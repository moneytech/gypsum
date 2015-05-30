# Copyright 2015, Jay Conrod. All rights reserved.
#
# This file is part of Gypsum. Use of this source code is governed by
# the GPL license that can be found in the LICENSE.txt file.


import unittest

import builtins
import bytecode
import externalization
import flags
import ids
import ir
import ir_types
import utils_test


class TestExternalization(unittest.TestCase):
    def setUp(self):
        self.package = ir.Package(ids.TARGET_PACKAGE_ID)
        self.rootClassType = ir_types.getRootClassType()
        self.nothingClassType = ir_types.getNothingClassType()
        self.otherPackage = ir.Package()
        self.packageLoader = utils_test.MockPackageLoader([self.otherPackage])
        self.externalizer = externalization.Externalizer(self.package, self.packageLoader)

        field = self.otherPackage.newField(ir.Name(["x"]), None, ir_types.I64Type,
                                           frozenset([flags.PUBLIC]))
        self.clas = self.otherPackage.addClass(ir.Name(["Foo"]), None, [], [self.rootClassType],
                                               None, None, [field], None,
                                               frozenset([flags.PUBLIC]))
        self.classTy = ir_types.ClassType(self.clas)
        ctor = self.otherPackage.addFunction(ir.Name([ir.CONSTRUCTOR_SUFFIX]),
                                             None, ir_types.UnitType,
                                             [], [], None, None,
                                             frozenset([flags.PUBLIC,
                                                        flags.METHOD]))
        self.clas.constructors = [ctor]
        method = self.otherPackage.addFunction(ir.Name(["m"]), None, ir_types.UnitType,
                                               [], [], None, None,
                                               frozenset([flags.PUBLIC, flags.METHOD]))
        self.clas.methods = [method]
        self.param = self.otherPackage.addTypeParameter(ir.Name(["T"]), None,
                                                        self.rootClassType,
                                                        self.nothingClassType,
                                                        frozenset([flags.STATIC]))
        self.dep = self.package.ensureDependency(self.otherPackage)
        self.externParam = self.externalizer.externalizeDefn(self.param)
        self.varTy = ir_types.VariableType(self.param)

    def getExtern(self, defn):
        dep = self.package.dependencies[defn.id.packageId.index]
        if isinstance(defn, ir.Global):
            externs = dep.externGlobals
        elif isinstance(defn, ir.Function):
            if flags.METHOD in defn.flags:
                externs = dep.externMethods
            else:
                externs = dep.externFunctions
        elif isinstance(defn, ir.Class):
            externs = dep.externClasses
        else:
            assert isinstance(defn, ir.TypeParameter)
            externs = dep.externTypeParameters
        externDefn = externs[defn.id.externIndex]
        return externDefn

    def checkExternPosition(self, defn):
        self.assertIn(flags.EXTERN, defn.flags)
        expected = self.getExtern(defn)
        self.assertIs(expected, defn)

    def testExternalizeGlobal(self):
        globl = self.otherPackage.addGlobal(ir.Name(["g"]), None, self.classTy,
                                            frozenset([flags.PUBLIC]))
        externGlobal = self.externalizer.externalizeDefn(globl)
        expected = ir.Global(ir.Name(["g"]), None, globl.id, self.classTy,
                             frozenset([flags.PUBLIC, flags.EXTERN]))
        self.assertEquals(expected, externGlobal)
        self.checkExternPosition(externGlobal)

    def testExternalizeFunction(self):
        function = self.otherPackage.addFunction(ir.Name(["f"]), None, self.classTy,
                                                 [self.param], [self.varTy], None, None,
                                                 frozenset([flags.PUBLIC]))
        externFunction = self.externalizer.externalizeDefn(function)
        expected = ir.Function(ir.Name(["f"]), None, function.id, self.classTy,
                               [self.externParam], [self.varTy], None, None,
                               frozenset([flags.PUBLIC, flags.EXTERN]))
        self.assertEquals(expected, externFunction)

    def testExternalizeClass(self):
        clas = self.otherPackage.addClass(ir.Name(["C"]), None,
                                          [self.param], [self.rootClassType],
                                          None, None, None, None, frozenset([flags.PUBLIC]))
        clasTy = ir_types.ClassType(clas, (self.varTy,))
        ctor = self.otherPackage.addFunction(ir.Name(["C", ir.CONSTRUCTOR_SUFFIX]),
                                             None, ir_types.UnitType, [self.param],
                                             [clasTy], None, None,
                                             frozenset([flags.PUBLIC, flags.METHOD]))
        clas.constructors = [ctor]
        field = self.otherPackage.newField(ir.Name(["C", "x"]), None,
                                           clasTy, frozenset([flags.PUBLIC]))
        clas.fields = [field]
        method = self.otherPackage.addFunction(ir.Name(["C", "f"]), None,
                                               ir_types.UnitType, [self.param], [clasTy],
                                               None, None,
                                               frozenset([flags.PUBLIC, flags.METHOD]))
        builtinMethod = \
            builtins.getBuiltinFunctionById(bytecode.BUILTIN_ROOT_CLASS_TO_STRING_ID)
        clas.methods = [method, builtinMethod]
        externClass = self.externalizer.externalizeDefn(clas)
        expected = ir.Class(ir.Name(["C"]), None, clas.id, [self.externParam],
                            [self.rootClassType], None, None, None, None,
                            frozenset([flags.PUBLIC, flags.EXTERN]))
        expectedCtor = ir.Function(ir.Name(["C", ir.CONSTRUCTOR_SUFFIX]),
                                   None, ctor.id, ir_types.UnitType, [self.externParam],
                                   [clasTy], None, None,
                                   frozenset([flags.PUBLIC, flags.METHOD, flags.EXTERN]))
        expected.constructors = [expectedCtor]
        expectedField = ir.Field(ir.Name(["C", "x"]), None, clasTy, frozenset([flags.PUBLIC]))
        expected.fields = [expectedField]
        expectedMethod = ir.Function(ir.Name(["C", "f"]),
                                     None, method.id, ir_types.UnitType, [self.externParam],
                                     [clasTy], None, None,
                                     frozenset([flags.PUBLIC, flags.METHOD, flags.EXTERN]))
        externBuiltinMethod = ir.Function(ir.Name(["Object", "to-string"]), None,
                                          builtinMethod.id, ir_types.getStringType(), [],
                                          [ir_types.getRootClassType()],
                                          None, None, frozenset([flags.EXTERN, flags.METHOD]))
        expected.methods = [expectedMethod, externBuiltinMethod]
        self.assertEquals(expected, externClass)

    def testExternalizeBuiltinMethodName(self):
        method = builtins.getBuiltinFunctionById(bytecode.BUILTIN_ROOT_CLASS_EQ_OP_ID)
        externMethod = self.externalizer.externalizeMethod(method, self.dep)
        self.assertIn(method.name.short(), self.package.strings)

    def testExternalizeTypeParameter(self):
        param = self.otherPackage.addTypeParameter(ir.Name(["S"]), None,
                                                   self.classTy, self.classTy,
                                                   frozenset([flags.STATIC]))
        externParam = self.externalizer.externalizeDefn(param)
        expected = ir.TypeParameter(ir.Name(["S"]), None, param.id, self.classTy, self.classTy,
                                    frozenset([flags.STATIC, flags.EXTERN]))
        self.assertEquals(expected, externParam)

    def testExternalizeBuiltinDefn(self):
        rootClass = builtins.getRootClass()
        externClass = self.externalizer.externalizeDefn(rootClass)
        self.assertIs(rootClass, externClass)

    def testExternalizeLocalDefn(self):
        localGlobal = self.package.addGlobal(ir.Name(["g"]), None,
                                             ir_types.UnitType, frozenset())
        externGlobal = self.externalizer.externalizeDefn(localGlobal)
        self.assertIs(localGlobal, externGlobal)