import btypes
import errors
from collections import defaultdict

import llvm.core as lc
import llvm.passes as lp

from llvm import LLVMException
from llvm.core import Module, Builder, Function, Type, Constant, GlobalVariable

#------------------------------------------------------------------------
# LLVM Types
#------------------------------------------------------------------------

int_type   = Type.int()
float_type = Type.double()
bool_type  = Type.int(1)
void_type  = Type.void()
char_type  = Type.int(8)

pointer = Type.pointer

string_type = pointer(char_type)

# { i32*, i32, i32* }
array_type = lambda elt_type: Type.struct([
    pointer(elt_type), # data         | (<type>)*
    int_type,          # dimensions   | int
    pointer(int_type), # strides      | int*
], name='ndarray_' + str(elt_type))

# opaque for now
blaze_type = lambda datashape: Type.opaque(name="blaze")

any_type = Type.void()

false = Constant.int(bool_type, 0)
true  = Constant.int(bool_type, 1)

#------------------------------------------------------------------------
# Type Relations
#------------------------------------------------------------------------

typemap = {
    'int'    : int_type,
    'float'  : float_type,
    'bool'   : bool_type,
    'str'    : string_type,
    'void'   : void_type,
    'any'    : any_type,
}

ptypemap = {
    'array' : array_type,
    'blaze' : blaze_type,
}

def arg_typemap(ty):
    if isinstance(ty, btypes.PType):
        cons = ptypemap[ty.cons.name]
        args = typemap[ty.arg.name]
        return pointer(cons(args))
    elif isinstance(ty, btypes.Type):
        return typemap[ty.name]
    else:
        raise NotImplementedError

float_instrs = {
    '>'  : lc.FCMP_OGT,
    '<'  : lc.FCMP_OLT,
    '==' : lc.FCMP_OEQ,
    '>=' : lc.FCMP_OGE,
    '<=' : lc.FCMP_OLE,
    '!=' : lc.FCMP_ONE
}

sing_instrs = {
    '>'  : lc.ICMP_SGT,
    '<'  : lc.ICMP_SLT,
    '==' : lc.ICMP_EQ,
    '>=' : lc.ICMP_SGE,
    '<=' : lc.ICMP_SLE,
    '!=' : lc.ICMP_NE
}

bool_instr = {
    '==' : lc.ICMP_EQ,
    '!=' : lc.ICMP_NE
}

bitwise = { '&&', '||' }

#------------------------------------------------------------------------
# Prelude
#------------------------------------------------------------------------

prelude = {
    'show_int'    : Type.function(void_type, [int_type], False),
    'show_float'  : Type.function(void_type, [float_type], False),
    'show_bool'   : Type.function(void_type, [bool_type], False),
    'show_string' : Type.function(void_type, [string_type], False),
}


def build_intrinsics():
    import intrinsics
    mod = Module.new('blir.intrinsics')

    ins = {}

    for name, intr in intrinsics.llvm_intrinsics.iteritems():
         # get the function signature
        name, retty, argtys = getattr(intrinsics, name)

        largtys = map(arg_typemap, argtys)
        lretty  = arg_typemap(retty)

        lfunc = Function.intrinsic(mod, intr, largtys)
        ins[name] = lfunc

    mod.verify()
    return mod, ins

#------------------------------------------------------------------------
# Function Level Codegen
#------------------------------------------------------------------------

CONSTANT_NAMING = '.conststr.%x'
MODULE_NAMING   = '.module.%x'

class LLVMEmitter(object):
    def __init__(self, name="blirkernel"):
        self.module = Module.new(name)

        # this is a stack based visitor
        self.function = None
        self.block = None
        self.builder = None

        self.globals = {}
        self.locals = {}
        self.arrays = defaultdict(dict)
        self.temps = {}

        self.intrinsics = {}
        self.add_prelude()

        intmod, intrinsics = build_intrinsics()

        self.module.link_in(intmod)
        self.globals.update(intrinsics)

    def visit_op(self, instr):
        for op in instr:
            opcode = op[0]
            op_args = op[1:]
            if hasattr(self, "op_"+opcode):
                getattr(self, "op_"+opcode)(*op_args)
            else:
                raise Exception("Can't translate opcode: op_"+opcode)

    def start_function(self, name, retty, argtypes):
        rettype = arg_typemap(retty)
        argtypes = [arg_typemap(arg) for arg in argtypes]
        func_type = Type.function(rettype, argtypes, False)

        self.function = Function.new(self.module, func_type, name)

        self.block = self.function.append_basic_block("entry")
        self.builder = Builder.new(self.block)
        self.exit_block = self.function.append_basic_block("exit")

        self.locals = {}
        self.temps = {}

        if rettype is not void_type:
            self.locals['retval'] = self.builder.alloca(rettype, "retval")

        # allow recursive calling
        self.globals[name] = self.function

    def end_function(self):
        self.builder.position_at_end(self.exit_block)

        if 'retval' in self.locals:
            retval = self.builder.load(self.locals['retval'])
            self.builder.ret(retval)
        else:
            self.builder.ret_void()

    def add_prelude(self):
        for name, function in prelude.iteritems():
            self.intrinsics[name] = Function.new(
                self.module,
                function,
                name
            )

    def add_block(self, name):
        return self.function.append_basic_block(name)

    def set_block(self, block):
        self.block = block
        self.builder.position_at_end(block)

    def cbranch(self, cond, true_block, false_block):
        self.builder.cbranch(self.temps[cond], true_block, false_block)

    def branch(self, next_block):
        self.builder.branch(next_block)

    def call(self, fn, argv):
        lfn = self.intrinsics[fn]
        self.builder.call(lfn, argv)

    def const(self, val):
        if isinstance(val, (int, long)):
            return Constant.int(int_type, val)
        elif isinstance(val, float):
            return Constant.real(float_type, val)
        elif isinstance(val, bool):
            return Constant.int(bool_type, int(val))
        elif isinstance(val, str):
            return Constant.stringz(val)
        else:
            raise NotImplementedError

    def lookup_var(self, name):
        # XXX replace this with just passing the symbol table
        if name in self.locals:
            return self.locals[name]
        else:
            return self.globals[name]

    def puts(self, val):
        if val.type == int_type:
            self.call('print_int', [val])
        elif val.type == float_type:
            self.call('print_float', [val])
        elif val.type == string_type:
            self.call('print_string', [val])
        else:
            raise NotImplementedError

    #------------------------------------------------------------------------
    # Opcodes
    #------------------------------------------------------------------------

    def op_LOAD_CONST(self, value, target):
        if isinstance(value, bool):
            self.temps[target] = Constant.int(bool_type, value)
        elif isinstance(value, int):
            self.temps[target] = Constant.int(int_type, value)
        elif isinstance(value, (float, long)):
            self.temps[target] = Constant.real(float_type, value)
        elif isinstance(value, str):
            # create null terminated string
            n = 0
            content = Constant.stringz(value)

            # create a unique global constant name, keep hashing
            # until we find one
            while True:
                try:
                    name = CONSTANT_NAMING % (abs(hash(value)) ^ n)
                    break
                except LLVMException:
                    n += 1
                    pass

            globalstr = self.module.add_global_variable(content.type, name)
            globalstr.initializer = content
            globalstr.linkage = lc.LINKAGE_LINKONCE_ODR
            self.temps[target] = globalstr.bitcast(pointer(content.type.element))
        else:
            raise NotImplementedError

    def op_ALLOC(self, ty, name):
        lty = typemap[ty.name]
        var = self.builder.alloca(lty, name)
        self.locals[name] = var

    def op_GLOBAL(self, ty, name):
        lty = typemap[ty.name]
        var = GlobalVariable.new(self.module, lty, name)
        var.initializer = self.const(ty.zero)
        self.globals[name] = var

    def op_LOAD(self, name, target):
        self.temps[target] = self.builder.load(self.lookup_var(name), target)

    def op_STORE(self, source, target):
        self.builder.store(self.temps[source], self.lookup_var(target))

    def op_ARRAYLOAD(self, source, index, target, cc=False):
        arr = self.arrays[source]
        data_ptr = arr['data']

        if cc:
            offset = self.const(0)

            for i, idx in enumerate(index.elts):
                ic = self.const(i)
                idxv = self.temps[idx.ssa_name]
                stride = arr['strides']
                stride_elt = self.builder.load(self.builder.gep(stride, [ic]))

                offset = self.builder.add(
                    offset,
                    self.builder.mul(stride_elt, idxv)
                )

        else:
            offset = self.temps[index]

        val = self.builder.gep(data_ptr, [offset])
        elt = self.builder.load(val)
        self.temps[target] = elt

    def op_ARRAYSTORE(self, source, index, target, cc=False):
        arr = self.arrays[source]
        data_ptr = arr['data']

        if cc:
            offset = self.const(0)

            for i, idx in enumerate(index.elts):
                ic = self.const(i)
                idxv = self.temps[idx.ssa_name]
                stride = arr['strides']
                stride_elt = self.builder.load(self.builder.gep(stride, [ic]))

                offset = self.builder.add(
                    offset,
                    self.builder.mul(stride_elt, idxv)
                )
        else:
            offset = self.temps[index]

        val = self.builder.gep(data_ptr, [offset])
        self.builder.store(self.temps[target], val)

    def op_BINARY_ADD(self, ty, left, right, val):
        lv = self.temps[left]
        rv = self.temps[right]

        if ty == btypes.int_type:
            self.temps[val] = self.builder.add(lv, rv, val)
        elif ty == btypes.float_type:
            self.temps[val] = self.builder.fadd(lv, rv, val)

    def op_BINARY_SUBTRACT(self, ty, left, right, val):
        lv = self.temps[left]
        rv = self.temps[right]

        if ty == btypes.int_type:
            self.temps[val] = self.builder.sub(lv, rv, val)
        elif ty == btypes.float_type:
            self.temps[val] = self.builder.fsub(lv, rv, val)

    def op_BINARY_MULTIPLY(self, ty, left, right, val):
        lv = self.temps[left]
        rv = self.temps[right]

        if ty == btypes.int_type:
            self.temps[val] = self.builder.mul(lv, rv, val)
        elif ty == btypes.float_type:
            self.temps[val] = self.builder.fmul(lv, rv, val)

    def op_BINARY_DIVIDE(self, ty, left, right, val):
        lv = self.temps[left]
        rv = self.temps[right]

        if ty == btypes.int_type:
            self.temps[val] = self.builder.sdiv(lv, rv, val)
        elif ty == btypes.float_type:
            self.temps[val] = self.builder.fsdiv(lv, rv, val)

    #------------------------------------------------------------------------
    # Unary Operators
    #------------------------------------------------------------------------

    def op_UNARY_POSITIVE(self, ty, source, target):
        self.temps[target] = self.temps[source]

    def op_UNARY_NEGATIVE(self, ty, source, target):

        if ty == btypes.int_type:
            self.temps[target] = self.builder.sub(
                Constant.int(int_type, 0),
                self.temps[source],
                target
            )
        elif ty == btypes.float_type:
            self.temps[target] = self.builder.fsub(
                Constant.real(float_type, 0.0),
                self.temps[source],
                target
            )

    def op_UNARY_NOT(self, ty, source, val):
        self.temps[val] = self.builder.icmp(lc.ICMP_EQ, self.temps[source], false, val)

    def op_COMPARE(self, op, ty, left, right, val):
        lv = self.temps[left]
        rv = self.temps[right]

        if ty == btypes.int_type:
            instr = sing_instrs[op]
            self.temps[val] = self.builder.icmp(instr, lv, rv, val)

        elif ty == btypes.float_type:
            instr = float_instrs[op]
            self.temps[val] = self.builder.fcmp(instr, lv, rv, val)

        # ick
        if ty == btypes.bool_type:
            if op in bitwise:
                if op == '&&':
                    self.temps[val] = self.builder.and_(lv, rv, val)
                elif op == '||':
                    self.temps[val] = self.builder.or_(lv, rv, val)
            else:
                instr = sing_instrs[op]
                self.temps[val] = self.builder.icmp(instr, lv, rv, val)

    #------------------------------------------------------------------------
    # Show Functions
    #------------------------------------------------------------------------

    def op_PRINT(self, ty, source):
        if ty == btypes.int_type:
            self.call('show_int', [self.temps[source]])
        elif ty == btypes.float_type:
            self.call('show_float', [self.temps[source]])
        elif ty == btypes.string_type:
            self.call('show_string', [self.temps[source]])
        elif ty == btypes.bool_type:
            tmp = self.builder.zext(self.temps[source], bool_type)
            self.call('show_bool', [tmp])
        else:
            raise NotImplementedError

    #------------------------------------------------------------------------
    # Extern Functions
    #------------------------------------------------------------------------

    def op_DEF_FOREIGN(self, name, retty, *argtys):
        _rettype = typemap[retty]
        _argtys = [typemap[arg] for arg in argtys]

        func_type = Type.function(_rettype, _argtys, False)
        self.globals[name] = Function.new(self.module, func_type, name)

    def op_CALL_FUNCTION(self, funcname, *args):
        target = args[-1]
        func = self.globals[funcname]
        argvals = [self.temps[name] for name in args[:-1]]
        self.temps[target] = self.builder.call(func, argvals)

    #------------------------------------------------------------------------
    # Return
    #------------------------------------------------------------------------

    def op_RETURN(self, ty, val=None):
        if ty == btypes.void_type:
            self.builder.branch(self.exit_block)
        else:
            self.builder.store(self.temps[val], self.locals['retval'])
            self.builder.branch(self.exit_block)

    #------------------------------------------------------------------------
    # Argument Variables
    #------------------------------------------------------------------------

    def op_LOAD_ARGUMENT(self, ty, name, num):
        # aggregate types, pass by reference
        if isinstance(ty, btypes.PType):

            # Blaze Types
            # -----------
            if ty.cons.name == 'blaze':
                blaze_ptr = self.function.args[num]
                self.locals[name] = blaze_ptr

            # NumPy ndarray
            # -------------
            else:
                struct_ptr = self.function.args[num]

                zero = self.const(0)
                one  = self.const(1)
                two  = self.const(2)

                data    = self.builder.gep(struct_ptr, [zero, zero], name=(name + '_data'))
                dims    = self.builder.gep(struct_ptr, [zero, one], name=(name + '_dims'))
                strides = self.builder.gep(struct_ptr, [zero, two], name=(name + '_strides'))

                self.arrays[name]['_struct'] = struct_ptr
                self.arrays[name]['_dtype'] = typemap[ty.arg.type.name]
                self.arrays[name]['data']    = self.builder.load(data)
                self.arrays[name]['dims']    = self.builder.load(dims)
                self.arrays[name]['strides'] = self.builder.load(strides)

                self.locals[name] = self.arrays[name]

        # concrete types, pass by value
        else:
            var = self.builder.alloca(int_type, name)
            self.builder.store(self.function.args[num], var)
            self.locals[name] = var

#------------------------------------------------------------------------
# Module Level Codegen
#------------------------------------------------------------------------

class BlockEmitter(object):

    def __init__(self, generator):
        self.cgen = generator

    def visit(self, block):
        while block is not None:
            name = "visit_%s" % type(block).__name__
            if hasattr(self, name):
                getattr(self, name)(block)
            block = block.next_block

    def generate_function(self, name, retty, argtyp, start_block):
        self.cgen.start_function(name, retty, argtyp)
        self.visit(start_block)
        self.cgen.end_function()
        return self.cgen.function

    def visit_BasicBlock(self, block):
        self.cgen.visit_op(block)

    def visit_IfBlock(self, block):
        self.cgen.visit_op(block)

        true_block  = self.cgen.add_block("if.then")
        false_block = self.cgen.add_block("if.else")
        endif_block = self.cgen.add_block("if.end")

        self.cgen.cbranch(block.testvar, true_block, false_block)

        # Visit the true-branch
        self.cgen.set_block(true_block)
        self.visit(block.true_branch)
        self.cgen.branch(endif_block)

        # Visit the false-branch
        self.cgen.set_block(false_block)
        self.visit(block.false_branch)
        self.cgen.branch(endif_block)

        self.cgen.set_block(endif_block)

    def visit_ForBlock(self, block):
        self.cgen.visit_op(block)

        # convienance aliases for the cgen parent
        builder = self.cgen.builder
        const   = self.cgen.const

        start = block.start_var
        stop  = block.stop_var
        step  = 1

        init_block = self.cgen.add_block('for.init')
        test_block = self.cgen.add_block('for.cond')
        body_block = self.cgen.add_block('for.body')
        end_block  = self.cgen.add_block("for.end")

        self.cgen.branch(init_block)
        self.cgen.set_block(init_block)

        # ------------------------------------------
        varname = block.var
        inc = builder.alloca(int_type, varname)
        self.cgen.locals[varname] = inc
        builder.store(self.cgen.temps[start], inc)
        # ------------------------------------------
        self.cgen.branch(test_block)
        self.cgen.set_block(test_block)
        # ------------------------------------------

        stopv = self.cgen.temps[stop]
        cond = builder.icmp(lc.ICMP_SLT, builder.load(inc), stopv)
        builder.cbranch(cond, body_block, end_block)

        # Generate the loop body
        self.cgen.set_block(body_block)
        self.visit(block.body)
        succ = builder.add(const(step), builder.load(inc))
        builder.store(succ, inc)

        self.cgen.branch(test_block)
        self.cgen.set_block(end_block)

    def visit_WhileBlock(self, block):
        test_block = self.cgen.add_block("while.cond")

        # ------------------------------------------
        self.cgen.branch(test_block)
        self.cgen.set_block(test_block)
        # ------------------------------------------

        self.cgen.visit_op(block)

        loop_block = self.cgen.add_block("while.body")
        after_loop = self.cgen.add_block("while.end")

        self.cgen.cbranch(block.testvar, loop_block, after_loop)

        # Generate the loop body
        self.cgen.set_block(loop_block)
        self.visit(block.body)
        self.cgen.branch(test_block)

        self.cgen.set_block(after_loop)

#------------------------------------------------------------------------
# Optimizer
#------------------------------------------------------------------------

class LLVMOptimizer(object):

    def __init__(self, module, opt_level=3):
        INLINER_THRESHOLD = 1000

        self.fpm = lp.FunctionPassManager.new(module)
        self.pmb = lp.PassManagerBuilder.new()
        self.pm  = lp.PassManager.new()

        self.pmb.opt_level = opt_level
        self.pmb.vectorize = True
        self.pmb.use_inliner_with_threshold(INLINER_THRESHOLD)

        self.pmb.populate(self.pm)
        self.pmb.populate(self.fpm)

    def runmodule(self, module):
        self.pm.run(module)

    def run(self, func):
        self.fpm.run(func)

    def diff(self, func, module):
        from difflib import Differ

        d = Differ()
        before = str(func)
        self.run(func)
        self.runmodule(module)
        after = str(func)

        diff = d.compare(before.splitlines(), after.splitlines())
        for line in diff:
            print line

#------------------------------------------------------------------------

def ddump_optimizer(source):
    import lexer
    import parser
    import cfg
    import typecheck
    import codegen

    with errors.listen():
        parse = parser.make_parser()

        ast = parse(source)
        typecheck.typecheck(ast)

        functions = cfg.ssa_pass(ast)
        cgen = codegen.LLVMEmitter()
        blockgen = codegen.BlockEmitter(cgen)

        for name, retty, argtys, start_block in functions:
            function = blockgen.generate_function(
                name,
                retty,
                argtys,
                start_block
            )

            optimizer = codegen.LLVMOptimizer(cgen.module)

            print 'Optimizer Diff'.center(80, '=')
            optimizer.diff(function, cgen.module)

#------------------------------------------------------------------------

if __name__ == '__main__':
    import sys

    if len(sys.argv) != 2:
        sys.stderr.write("Usage: %s filename\n" % sys.argv[0])
        raise SystemExit(1)

    source = open(sys.argv[1]).read()
    ddump_optimizer(source)
