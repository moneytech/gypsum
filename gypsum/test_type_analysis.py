# Copyright Jay Conrod. All rights reserved.
#
# This file is part of Gypsum. Use of this source code is governed by
# the GPL license that can be found in the LICENSE.txt file.


import unittest

from compile_info import *
from errors import *
from ids import *
from inheritance_analysis import *
from ir import *
from ir_types import *
from lexer import *
from location import NoLoc
from parser import *
from scope_analysis import *
from type_analysis import *
from flags import *
from builtins import getRootClass, getStringClass, getNothingClass, getExceptionClass
from utils_test import (
    FUNCTION_SOURCE,
    FakePackageLoader,
    OPTION_SOURCE,
    TUPLE_SOURCE,
    TestCaseWithDefinitions,
)
from name import (
    CLASS_INIT_SUFFIX,
    CONSTRUCTOR_SUFFIX,
    EXISTENTIAL_SUFFIX,
    Name,
    RECEIVER_SUFFIX,
)


class TestTypeAnalysis(TestCaseWithDefinitions):
    def analyzeFromSource(self,
                          source,
                          name=None,
                          packageNames=None,
                          packageLoader=None,
                          isUsingStd=False):
        assert packageNames is None or packageLoader is None
        filename = "(test)"
        tokens = lex(filename, source)
        ast = parse(filename, tokens)
        if name is None:
            name = Name(["test"])
        if packageNames is None:
            packageNames = []
        if packageLoader is None:
            packageNameFromString = lambda s: Name.fromString(s, isPackageName=True)
            packageLoader = FakePackageLoader(map(packageNameFromString, packageNames))
        package = Package(TARGET_PACKAGE_ID, name=name)
        info = CompileInfo(ast,
                           package=package,
                           packageLoader=packageLoader,
                           isUsingStd=isUsingStd)
        analyzeDeclarations(info)
        analyzeTypeDeclarations(info)
        analyzeInheritance(info)
        analyzeTypes(info)
        return info

    # Module
    def testRecursiveNoType(self):
        source = "def f(x) = f(x)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testRecursiveParamTypeOnly(self):
        source = "def f(x: i32) = f(x)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testRecursiveReturnTypeOnly(self):
        source = "def f(x): i32 = f(x)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testBlankParamNoType(self):
        source = "def f(_): i64 = 0"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testBlankParamWithType(self):
        source = "def f(_: i64): i64 = 0"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals([I64Type], f.parameterTypes)

    def testIntLiteralParam(self):
        source = "def f(12): i64 = 0"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testNullLiteralParam(self):
        source = "def f(null): i64 = 0"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testTupleParam(self):
        source = TUPLE_SOURCE + \
                 "def f((x: String, y: String)) = x"
        info = self.analyzeFromSource(source, name=STD_NAME)
        tupleClass = info.package.findClass(name="Tuple2")
        f = info.package.findFunction(name="f")
        self.assertEquals([ClassType(tupleClass, (getStringType(), getStringType()))],
                          f.parameterTypes)
        self.assertEquals(getStringType(), f.returnType)

    def testTupleParamWithBadElement(self):
        source = TUPLE_SOURCE + \
                 "def f((x: String, \"bar\")) = x"
        self.assertRaises(ScopeException, self.analyzeFromSource, source)

    def testTupleParamWithPrimitiveElement(self):
        source = TUPLE_SOURCE + \
                 "def f((x: String, 12)) = x"
        self.assertRaises(ScopeException, self.analyzeFromSource, source)

    def testTupleParamWithUntypedElement(self):
        source = TUPLE_SOURCE + \
                 "def f((x: String, y)) = x"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testValueParam(self):
        foo = Package(name=Name(["foo"]))
        foo.addGlobal(Name(["bar"]), type=UnitType, flags=frozenset([PUBLIC, LET]))
        source = "def f(foo.bar) = 12"
        self.assertRaises(TypeException, self.analyzeFromSource,
                          source, packageLoader=FakePackageLoader([foo]))

    def testDestructureParam(self):
        source = "def f(foo(x: String)) = 12"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testRecursiveGlobal(self):
        source = "def f = x\n" + \
                 "let x = f"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testRecursiveFullType(self):
        source = "def f(x: i32): i32 = f(x)"
        info = self.analyzeFromSource(source)
        f = info.package.functions[0]
        self.assertEquals(I32Type, f.returnType)
        self.assertEquals([I32Type], f.parameterTypes)

    def testMutuallyRecursiveNoType(self):
        source = "def f(x) = g(x)\n" + \
                 "def g(x) = f(x)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testMutuallyRecursiveWithType(self):
        source = "def f(x: i32): i32 = g(x)\n" + \
                 "def g(x: i32): i32 = f(x)"
        info = self.analyzeFromSource(source)
        # pass if this does not raise an error

    def testNoReturnTypeRequiresBody(self):
        source = "abstract class C\n" + \
                 "  abstract def f"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    # Definitions
    def testConstructorsMayNotHaveReturnType(self):
        source = "class Foo\n" + \
                 "  def this: i32 = 12"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testConstructorsMayNotReturnValue(self):
        source = "class Foo\n" + \
                 "  def this = return 12"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPrimaryConstructorsReturnUnit(self):
        source = "class Foo()"
        info = self.analyzeFromSource(source)
        clas = info.package.findClass(name="Foo")
        self.assertEquals(UnitType, clas.constructors[0].returnType)

    def testPrimaryUnaryConstructorReturnUnit(self):
        source = "class Foo(x: i32)"
        info = self.analyzeFromSource(source)
        clas = info.package.findClass(name="Foo")
        ctor = clas.constructors[0]
        self.assertEquals(UnitType, ctor.returnType)
        self.assertEquals([ClassType(clas), I32Type], ctor.parameterTypes)
        self.assertEquals([ClassType(clas), I32Type], [v.type for v in ctor.variables])

    def testSecondaryConstructorsReturnUnit(self):
        source = "class Foo\n" + \
                 "  def this = 12"
        info = self.analyzeFromSource(source)
        clas = info.package.findClass(name="Foo")
        self.assertEquals(UnitType, clas.constructors[0].returnType)

    def testCallSuperWithoutPrimaryOrDefaultConstructor(self):
        source = "class Foo(x: i64)\n" + \
                 "class Bar <: Foo(12)\n" + \
                 "  def this(x: i64) =\n" + \
                 "    super(x)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPrimaryConstructorCallSuper(self):
        source = "class Foo(x: i64)\n" + \
                 "class Bar(y: i64) <: Foo(y)"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type,
                          info.getType(info.ast.modules[0].definitions[1].superArgs[0]))

    def testDefaultConstructorCallSuper(self):
        source = "class Foo(x: i64)\n" + \
                 "class Bar <: Foo(12)"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type,
                          info.getType(info.ast.modules[0].definitions[1].superArgs[0]))

    def testInitializerAndDefaultConstructorThisType(self):
        source = "class Foo"
        info = self.analyzeFromSource(source)
        clas = info.package.findClass(name="Foo")
        thisType = ClassType(clas)
        ctor = clas.constructors[0]
        self.assertEquals([thisType], clas.constructors[0].parameterTypes)
        self.assertEquals(self.makeVariable(Name(["Foo", CONSTRUCTOR_SUFFIX, RECEIVER_SUFFIX]),
                                            type=thisType,
                                            kind=PARAMETER, flags=frozenset([LET])),
                          ctor.variables[0])
        init = clas.initializer
        self.assertEquals([thisType], clas.constructors[0].parameterTypes)
        self.assertEquals(self.makeVariable(Name(["Foo", CLASS_INIT_SUFFIX, RECEIVER_SUFFIX]),
                                            type=thisType,
                                            kind=PARAMETER, flags=frozenset([LET])),
                          init.variables[0])

    def testVariableWithoutType(self):
        self.assertRaises(TypeException, self.analyzeFromSource, "var x")

    def testVariableWithSubtype(self):
        self.assertRaises(TypeException, self.analyzeFromSource, "let x: String = Object()")

    def testConstructorBeforeField(self):
        source = "class Foo\n" + \
                 "  def this(x: i32) =\n" + \
                 "    this.x = x\n" + \
                 "  var x: i32"
        info = self.analyzeFromSource(source)
        body = info.ast.modules[0].definitions[0].members[0].body
        self.assertEquals(I32Type, info.getType(body.statements[0].left))

    def testUnusedDefaultConstructor(self):
        source = "class Foo"
        info = self.analyzeFromSource(source)
        clas = info.package.findClass(name="Foo")
        ctor = clas.constructors[0]
        self.assertEquals([ClassType(clas)], ctor.parameterTypes)
        self.assertEquals(UnitType, ctor.returnType)

    def testUseBeforeCapturedVar(self):
        source = "def f =\n" + \
                 "  def g =\n" + \
                 "    i = 1\n" + \
                 "  var i = 0"
        info = self.analyzeFromSource(source)
        statements = info.ast.modules[0].definitions[0].body.statements
        self.assertEquals(I64Type, info.getType(statements[0].body.statements[0].left))
        self.assertEquals(I64Type, info.getType(statements[1].pattern))

    # Expressions
    def testIntLiteral(self):
        source = "var x = 12"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findGlobal(name="x").type)

    def testIntLiteralBounds(self):
        self.assertRaises(TypeException, self.analyzeFromSource, "var x = 256i8")
        self.assertRaises(TypeException, self.analyzeFromSource, "var x = -129i8")

    def testIntLiteralWidths(self):
        self.assertRaises(TypeException, self.analyzeFromSource, "var x = 0i7")

    def testFloatLiteral(self):
        source = "var x = 1.200000\n" + \
                 "var y = 3.400000f32"
        info = self.analyzeFromSource(source)
        self.assertEquals(F64Type, info.package.findGlobal(name="x").type)
        self.assertEquals(F32Type, info.package.findGlobal(name="y").type)

    def testFloatLiteralWidths(self):
        source = "var x = 1.200000f42"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testStringLiteral(self):
        source = "var s = \"foo\""
        info = self.analyzeFromSource(source)
        self.assertEquals(getStringType(), info.package.findGlobal(name="s").type)

    def testBooleanLiteral(self):
        source = "var x = true"
        info = self.analyzeFromSource(source)
        self.assertEquals(BooleanType, info.package.findGlobal(name="x").type)

    def testNullLiteral(self):
        source = "var x = null"
        info = self.analyzeFromSource(source)
        self.assertEquals(getNullType(), info.package.findGlobal(name="x").type)

    def testLocalVariable(self):
        source = "def f(x: i32) = x"
        info = self.analyzeFromSource(source)
        self.assertEquals(I32Type, info.package.findFunction(name="f").variables[0].type)
        self.assertEquals(I32Type, info.getType(info.ast.modules[0].definitions[0].body))

    def testFunctionVariable(self):
        source = "def f: i32 = 12i32\n" + \
                 "def g = f"
        info = self.analyzeFromSource(source)
        self.assertEquals(I32Type, info.package.findFunction(name="g").returnType)
        self.assertEquals(I32Type, info.getType(info.ast.modules[0].definitions[1].body))

    def testPackageVariable(self):
        source = "var x = foo"
        info = self.analyzeFromSource(source, packageNames=["foo"])
        packageType = getPackageType()
        self.assertEquals(packageType, info.package.findGlobal(name="x").type)
        self.assertEquals(packageType, info.getType(info.ast.modules[0].definitions[0].expression))
        self.assertEquals(info.packageNames[0], info.package.dependencies[0].name)
        self.assertEquals(0, info.package.dependencies[0].package.id.index)

    def testPackageVariablePrefix(self):
        source = "var x = foo"
        self.assertRaises(TypeException,
                          lambda: self.analyzeFromSource(source, packageNames=["foo.bar"]))

    def testPackageVariableWithPrefix(self):
        source = "var x = foo"
        info = self.analyzeFromSource(source, packageNames=["foo", "foo.bar"])
        packageType = getPackageType()
        self.assertEquals(packageType, info.package.findGlobal(name="x").type)

    def testThisExpr(self):
        source = "class Foo\n" + \
                 "  var x = this"
        info = self.analyzeFromSource(source)
        clas = info.package.findClass(name="Foo")
        self.assertEquals(ClassType(clas),
                          info.getType(info.ast.modules[0].definitions[0].members[0].expression))

    def testSuperExpr(self):
        source = "class Foo\n" + \
                 "class Bar <: Foo\n" + \
                 "  def this = super()"
        info = self.analyzeFromSource(source)
        foo = info.package.findClass(name="Foo")
        expr = info.ast.modules[0].definitions[1].members[0].body.callee
        self.assertEquals(ClassType(foo), info.getType(expr))

    def testBlockEmpty(self):
        source = "def f = ()"
        info = self.analyzeFromSource(source)
        self.assertEquals(UnitType, info.package.findFunction(name="f").returnType)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[0].body))

    def testBlockSingleExpr(self):
        source = "def f =\n" + \
                 "  12"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findFunction(name="f").returnType)
        self.assertEquals(I64Type, info.getType(info.ast.modules[0].definitions[0].body))

    def testBlockEndsWithDefn(self):
        source = "def f =\n" + \
                 "  12\n" + \
                 "  var x = 34"
        info = self.analyzeFromSource(source)
        self.assertEquals(UnitType, info.package.findFunction(name="f").returnType)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[0].body))
        self.assertFalse(info.hasType(info.ast.modules[0].definitions[0].body.statements[1]))

    def testAssign(self):
        source = "def f(x: i64) =\n" + \
                 "  x = 12"
        info = self.analyzeFromSource(source)
        self.assertEquals(UnitType, info.package.findFunction(name="f").returnType)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[0].body))

    def testAssignWrongType(self):
        source = "def f(x: i32) =\n" + \
                 "  x = true"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPropertyNonExistant(self):
        source = "class Foo\n" + \
                 "def f(o: Foo) = o.x"
        self.assertRaises(ScopeException, self.analyzeFromSource, source)

    def testPropertyField(self):
        source = "class Foo\n" + \
                 "  var x: boolean\n" + \
                 "def f(o: Foo) = o.x"
        info = self.analyzeFromSource(source)
        self.assertEquals(BooleanType, info.package.findFunction(name="f").returnType)
        self.assertEquals(BooleanType, info.getType(info.ast.modules[0].definitions[1].body))

    def testPropertyNullaryMethod(self):
        source = "class Foo\n" + \
                 "  def m = false\n" + \
                 "def f(o: Foo) = o.m"
        info = self.analyzeFromSource(source)
        self.assertEquals(BooleanType, info.package.findFunction(name="f").returnType)
        self.assertEquals(BooleanType, info.package.findFunction(name="Foo.m").returnType)
        self.assertEquals(BooleanType, info.getType(info.ast.modules[0].definitions[1].body))

    def testPropertyPackage(self):
        source = "var x = foo.bar"
        info = self.analyzeFromSource(source, packageNames=["foo.bar"])
        packageType = getPackageType()
        self.assertEquals(packageType, info.getType(info.ast.modules[0].definitions[0].expression))

    def testPropertyPackagePrefix(self):
        source = "var x = foo.bar"
        self.assertRaises(TypeException,
                          lambda: self.analyzeFromSource(source, packageNames=["foo.bar.baz"]))

    def testPropertyPackageWithPrefix(self):
        source = "var x = foo.bar"
        info = self.analyzeFromSource(source, packageNames=["foo.bar", "foo.bar.baz"])
        packageType = getPackageType()
        self.assertEquals(packageType, info.getType(info.ast.modules[0].definitions[0].expression))

    def testPropertyForeignGlobal(self):
        source = "var x = foo.bar"
        foo = Package(name=Name(["foo"]))
        bar = foo.addGlobal(Name(["bar"]), sourceName="bar",
                            type=UnitType, flags=frozenset([PUBLIC, LET]))
        info = self.analyzeFromSource(source, packageLoader=FakePackageLoader([foo]))
        x = info.package.findGlobal(name="x")
        self.assertEquals(UnitType, x.type)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[0].expression))

    def testPropertyForeignFunction(self):
        source = "var x = foo.bar"
        foo = Package(name=Name(["foo"]))
        bar = foo.addFunction(Name(["bar"]), sourceName="bar",
                              returnType=UnitType, typeParameters=[],
                              parameterTypes=[], flags=frozenset([PUBLIC]))
        info = self.analyzeFromSource(source, packageLoader=FakePackageLoader([foo]))
        x = info.package.findGlobal(name="x")
        self.assertEquals(UnitType, x.type)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[0].expression))

    def testPropertyForeignCtor(self):
        foo = Package(name=Name(["foo"]))
        bar = foo.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                           supertypes=[getRootClassType()],
                           constructors=[], fields=[],
                           methods=[], flags=frozenset([PUBLIC]))
        barType = ClassType(bar)
        ctor = foo.addFunction(Name(["Bar", CONSTRUCTOR_SUFFIX]),
                               returnType=UnitType, typeParameters=[], parameterTypes=[barType],
                               flags=frozenset([PUBLIC, METHOD, CONSTRUCTOR]),
                               definingClass=bar)
        bar.constructors.append(ctor)
        packageLoader = FakePackageLoader([foo])

        source = "var x = foo.Bar()"
        info = self.analyzeFromSource(source, packageLoader=packageLoader)
        x = info.package.findGlobal(name="x")
        self.assertEquals(barType, x.type)
        callInfo = info.getCallInfo(info.ast.modules[0].definitions[0].expression)

    def testCallForeignFunctionWithArg(self):
        source = "var x = foo.bar(12)"
        foo = Package(name=Name(["foo"]))
        bar = foo.addFunction(Name(["bar"]), sourceName="bar",
                              returnType=I64Type, typeParameters=[],
                              parameterTypes=[I64Type], flags=frozenset([PUBLIC]))
        info = self.analyzeFromSource(source, packageLoader=FakePackageLoader([foo]))
        x = info.package.findGlobal(name="x")
        self.assertEquals(I64Type, x.type)

    def testCallForeignFunctionWithTypeArg(self):
        source = "var x = foo.bar[String](\"baz\")"
        foo = Package(name=Name(["foo"]))
        T = foo.addTypeParameter(None, Name(["T"]), upperBound=getRootClassType(),
                                 lowerBound=getNothingClassType(), flags=frozenset([STATIC]))
        Tty = VariableType(T)
        bar = foo.addFunction(Name(["bar"]), sourceName="bar",
                              returnType=Tty, typeParameters=[T],
                              parameterTypes=[Tty], flags=frozenset([PUBLIC]))
        info = self.analyzeFromSource(source, packageLoader=FakePackageLoader([foo]))
        x = info.package.findGlobal(name="x")
        self.assertEquals(getStringType(), x.type)

    def testCallFunctionWithForeignTypeArg(self):
        otherPackage = Package(name=Name(["foo"]))
        clas = otherPackage.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                     supertypes=[getRootClassType()],
                                     constructors=[], fields=[],
                                     methods=[], flags=frozenset([PUBLIC]))
        loader = FakePackageLoader([otherPackage])
        source = "def id[static T](x: T) = x\n" + \
                 "def f(x: foo.Bar) = id[foo.Bar](x)"
        info = self.analyzeFromSource(source, packageLoader=loader)
        expectedType = ClassType(clas)
        fAst = info.ast.modules[0].definitions[1]
        self.assertEquals(expectedType, info.getType(fAst.parameters[0]))
        self.assertEquals(expectedType, info.getType(fAst.body.typeArguments[0]))
        self.assertEquals(expectedType, info.getType(fAst.body.arguments[0]))
        self.assertEquals(expectedType, info.getType(fAst.body))

    def testLoadFromForeignClass(self):
        fooPackage = Package(name=Name(["foo"]))
        clas = fooPackage.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                   supertypes=[getRootClassType()],
                                   constructors=[], fields=[],
                                   methods=[], flags=frozenset([PUBLIC]))
        fooPackage.addField(clas, Name(["Bar", "x"]), sourceName="x",
                            type=I64Type, flags=frozenset([PUBLIC]))
        loader = FakePackageLoader([fooPackage])

        source = "def f(o: foo.Bar) = o.x"
        info = self.analyzeFromSource(source, packageLoader=loader)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testStoreToForeignClass(self):
        fooPackage = Package(name=Name(["foo"]))
        clas = fooPackage.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                   supertypes=[getRootClassType()],
                                   constructors=[], fields=[],
                                   methods=[], flags=frozenset([PUBLIC]))
        fooPackage.addField(clas, Name(["Bar", "x"]), sourceName="x",
                            type=I64Type, flags=frozenset([PUBLIC]))
        loader = FakePackageLoader([fooPackage])

        source = "def f(o: foo.Bar) =\n" + \
                 "  o.x = 12"
        info = self.analyzeFromSource(source, packageLoader=loader)
        f = info.package.findFunction(name="f")
        self.assertEquals(UnitType, f.returnType)

    def testCallForeignMethod(self):
        fooPackage = Package(name=Name(["foo"]))
        clas = fooPackage.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                   supertypes=[getRootClassType()],
                                   constructors=[], fields=[],
                                   methods=[], flags=frozenset([PUBLIC]))
        m = fooPackage.addFunction(Name(["Bar", "m"]), sourceName="m",
                                   returnType=I64Type, typeParameters=[],
                                   parameterTypes=[ClassType(clas)],
                                   flags=frozenset([PUBLIC, METHOD]),
                                   definingClass=clas)
        clas.methods.append(m)
        loader = FakePackageLoader([fooPackage])

        source = "def f(o: foo.Bar) = o.m"
        info = self.analyzeFromSource(source, packageLoader=loader)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testLoadFromInheritedForeignClass(self):
        fooPackage = Package(name=Name(["foo"]))
        clas = fooPackage.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                   supertypes=[getRootClassType()],
                                   constructors=[], fields=[],
                                   methods=[], flags=frozenset([PUBLIC]))
        ty = ClassType(clas)
        ctor = fooPackage.addFunction(Name(["Bar", CONSTRUCTOR_SUFFIX]),
                                      returnType=UnitType, typeParameters=[],
                                      parameterTypes=[ty],
                                      flags=frozenset([PUBLIC, METHOD]),
                                      definingClass=clas)
        clas.constructors = [ctor]
        fooPackage.addField(clas, Name(["Bar", "x"]), sourceName="x",
                            type=I64Type, flags=frozenset([PUBLIC]))
        packageLoader = FakePackageLoader([fooPackage])

        source = "class Baz <: foo.Bar\n" + \
                 "def f(o: Baz) = o.x"
        info = self.analyzeFromSource(source, packageLoader=packageLoader)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testCallInInheritedForeignClass(self):
        fooPackage = Package(name=Name(["foo"]))
        clas = fooPackage.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                   supertypes=[getRootClassType()],
                                   constructors=[], fields=[],
                                   methods=[], flags=frozenset([PUBLIC]))
        ty = ClassType(clas)
        ctor = fooPackage.addFunction(Name(["Bar", CONSTRUCTOR_SUFFIX]),
                                      returnType=UnitType, typeParameters=[],
                                      parameterTypes=[ty],
                                      flags=frozenset([PUBLIC, METHOD]),
                                      definingClass=clas)
        clas.constructors.append(ctor)
        m = fooPackage.addFunction(Name(["Bar", "m"]), sourceName="m",
                                   returnType=ty, typeParameters=[], parameterTypes=[ty],
                                   flags=frozenset([PUBLIC, METHOD]),
                                   definingClass=clas)
        clas.methods.append(m)
        packageLoader = FakePackageLoader([fooPackage])

        source = "class Baz <: foo.Bar\n" + \
                 "def f(o: Baz) = o.m"
        info = self.analyzeFromSource(source, packageLoader=packageLoader)
        f = info.package.findFunction(name="f")
        self.assertEquals(ty, f.returnType)

    def testProjectClassFromTypeParameter(self):
        source = "class Foo\n" + \
                 "  class Bar\n" + \
                 "def f[static T <: Foo](x: T.Bar) = ()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testProjectTypeParameterFromClass(self):
        source = "class Foo[static T]\n" + \
                 "def f(x: Foo[String].T) = x"
        self.assertRaises(ScopeException, self.analyzeFromSource, source)

    def testCallMethodWithNullableReceiver(self):
        source = "class Foo\n" + \
                 "  def m = ()\n" + \
                 "def f(o: Foo?) = o.m"
        info = self.analyzeFromSource(source)
        self.assertEquals(UnitType, info.package.findFunction(name="f").returnType)

    def testIntegerMethod(self):
        source = "def f(n: i64) = n.to-i32"
        info = self.analyzeFromSource(source)
        self.assertEquals(I32Type, info.package.findFunction(name="f").returnType)

    def testCallStaticMethodFromMethod(self):
        source = "class Foo\n" + \
                 "  static def f = 12\n" + \
                 "  def g = f"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findFunction(name="Foo.g").returnType)

    def testCallOverloadedStaticMethodFromMethod(self):
        source = "class Foo\n" + \
                 "  static def f(x: i64) = x\n" + \
                 "  static def f(x: String) = x\n" + \
                 "  def g = f(12)"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findFunction(name="Foo.g").returnType)

    def testCallStaticMethodOverloadedWithNonStaticMethodFromMethod(self):
        source = "class Foo\n" + \
                 "  static def f(x: i64) = x\n" + \
                 "  def f(x: String) = x\n" + \
                 "  def g1 = f(12)\n" + \
                 "  def g2 = f(\"bar\")"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findFunction(name="Foo.g1").returnType)
        self.assertEquals(getStringType(), info.package.findFunction(name="Foo.g2").returnType)

    def testStaticDoesNotReduceOverloadAmbiguity(self):
        source = "class Foo\n" + \
                 "  static def f(x: i64) = x\n" + \
                 "  def f(x: i64) = x\n" + \
                 "  static def g = f"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCallStaticMethodFromGlobal(self):
        source = "class Foo\n" + \
                 "  static def f = 12\n" + \
                 "def g = Foo.f"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findFunction(name="g").returnType)

    def testCallStaticMethodFromGlobalWithTypeArg(self):
        source = "class Foo[static T]\n" + \
                 "  static def f(x: T) = x\n" + \
                 "def g = Foo[String].f(\"foo\")"
        info = self.analyzeFromSource(source)
        self.assertEquals(getStringType(), info.package.findFunction(name="g").returnType)

    def testCallStaticInheritedMethodFromGlobal(self):
        source = "class Foo\n" + \
                 "  static def f = 12\n" + \
                 "class Bar <: Foo\n" + \
                 "def g = Bar.f"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findFunction(name="g").returnType)

    def testCallStaticInheritedMethodFromGlobalWithTypeArg(self):
        source = "class Foo[static T]\n" + \
                 "  static def f(x: T) = x\n" + \
                 "class Bar <: Foo[String]\n" + \
                 "def g = Bar.f(\"foo\")"
        info = self.analyzeFromSource(source)
        self.assertEquals(getStringType(), info.package.findFunction(name="g").returnType)

    def testCallStaticMethodFromGlobalMissingTypeArg(self):
        source = "class Foo[static T]\n" + \
                 "  static def f(x: T) = x\n" + \
                 "def g = Foo.f"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testForeignClassWithOverrideMethod(self):
        fooPackage = Package(name=Name(["foo"]))
        clas = fooPackage.addClass(name=Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                   supertypes=[getRootClassType()],
                                   constructors=[], fields=[], methods=[],
                                   flags=frozenset([PUBLIC]))
        ty = ClassType(clas)
        rootClass = getRootClass()
        rootToString = rootClass.findMethodBySourceName("to-string")
        method = fooPackage.addFunction(name=Name(["Bar", "to-string"]), sourceName="to-string",
                                        returnType=getStringType(), typeParameters=[],
                                        parameterTypes=[ty],
                                        flags=frozenset([PUBLIC, METHOD, OVERRIDE]),
                                        definingClass=clas, overrides=[rootToString])
        clas.methods.append(method)
        packageLoader = FakePackageLoader([fooPackage])

        source = "import foo.Bar\n" + \
                 "def f(bar: Bar) = bar.to-string"
        info = self.analyzeFromSource(source, packageLoader=packageLoader)
        useInfo = info.getUseInfo(info.ast.modules[0].definitions[-1].body)
        self.assertIs(method.id, useInfo.defnInfo.irDefn.id)

    def testCall(self):
        source = "def f(x: i64, y: boolean) = x\n" + \
                 "def g = f(1, true)"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findFunction(name="g").returnType)
        self.assertEquals(I64Type, info.getType(info.ast.modules[0].definitions[1].body))

    def testCallVariable(self):
        source = "let f = lambda true\n" + \
                 "let g = f()"
        info = self.analyzeFromSource(source)
        f = info.package.findGlobal(name="f")
        g = info.package.findGlobal(name="g")
        self.assertEquals(BooleanType, info.package.findGlobal(name="g").type)
        astCall = info.ast.modules[0].definitions[-1].expression
        self.assertIs(f, info.getUseInfo(astCall.callee).defnInfo.irDefn)
        call = info.package.findFunction(name=Name([LAMBDA_SUFFIX]))
        self.assertIs(call, info.getUseInfo(astCall).defnInfo.irDefn)
        self.assertTrue(info.hasCallInfo(astCall))

    def testCallVariableValue(self):
        source = "let f = lambda true\n" + \
                 "let g = (f)()"
        info = self.analyzeFromSource(source)
        self.assertEquals(BooleanType, info.package.findGlobal(name="g").type)

    def testCallField(self):
        source = FUNCTION_SOURCE + \
                 "class Box(f: Function1[String, String])\n" + \
                 "def g(box: Box, s: String) = box.f(s)"
        info = self.analyzeFromSource(source)
        Box = info.package.findClass(name="Box")
        f = Box.findFieldBySourceName("f")
        self.assertEquals(getStringType(), info.package.findFunction(name="g").returnType)
        astCall = info.ast.modules[0].definitions[-1].body
        self.assertEquals(f.name, info.getUseInfo(astCall.callee).defnInfo.irDefn.name)
        call = info.package.findFunction(name="Function1.call")
        self.assertIs(call, info.getUseInfo(astCall).defnInfo.irDefn)
        self.assertTrue(info.hasCallInfo(astCall))

    def testCallFieldValue(self):
        source = FUNCTION_SOURCE + \
                 "class Box(f: Function1[String, String])\n" + \
                 "def f(box: Box, s: String) = (box.f)(s)"
        info = self.analyzeFromSource(source)
        self.assertEquals(getStringType(), info.package.findFunction(name="f").returnType)

    def testCallLambdaValue(self):
        source = "let x = (lambda (y: i64) y)(12)"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findGlobal(name="x").type)

    def testCallLambdaWithImplicitTypeArgument(self):
        source = "def f[static T] = (lambda (x: i64) x)(12)"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findFunction(name="f").returnType)

    def testCallWrongNumberOfArgs(self):
        source = "def f(x: i32, y: boolean) = x\n" + \
                 "def g = f(1)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCtorWrongNumberOfArgs(self):
        source = "class Foo\n" + \
                 "  def this(x: i32, y: i32) = ()\n" + \
                 "def f = Foo(12)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testMethodWrongNumberOfArgs(self):
        source = "class Foo\n" + \
                 "  def m(x: i32) = x\n" + \
                 "def f(o: Foo) = o.m(1, 2)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCallWrongArgs(self):
        source = "def f(x: i32, y: boolean) = x\n" + \
                 "def g = f(true, 1)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCallTypeArgOutOfBounds(self):
        source = "def f[static T <: String] = ()\n" + \
                 "var g = f[Object]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCallNullaryCtor(self):
        info = self.analyzeFromSource("class Foo\n" +
                                      "  def this = ()\n" +
                                      "def f = Foo()")
        clas = info.package.findClass(name="Foo")
        function = info.package.findFunction(name="f")
        self.assertEquals(ClassType(clas, ()), function.returnType)
        self.assertEquals(ClassType(clas, ()), info.getType(info.ast.modules[0].definitions[1].body))

    def testCallCtorWithArgs(self):
        info = self.analyzeFromSource("class Foo\n" +
                                      "  def this(x: i64, y: i64) = ()\n" +
                                      "def f = Foo(1, 2)\n")
        clas = info.package.findClass(name="Foo")
        function = info.package.findFunction(name="f")
        self.assertEquals(ClassType(clas, ()), function.returnType)
        self.assertEquals(ClassType(clas, ()), info.getType(info.ast.modules[0].definitions[1].body))

    def testNegExpr(self):
        source = "def f = -12"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.package.findFunction(name="f").returnType)
        self.assertEquals(I64Type, info.getType(info.ast.modules[0].definitions[0].body))

    def testAddExpr(self):
        source = "def f = 12 + 34"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.getType(info.ast.modules[0].definitions[0].body))

    def testStringConcatExpr(self):
        source = "def f = \"foo\" + \"bar\""
        info = self.analyzeFromSource(source)
        self.assertEquals(getStringType(), info.getType(info.ast.modules[0].definitions[0].body))

    def testBinopAssignExpr(self):
        info = self.analyzeFromSource("def f =\n" +
                                      "  var x = 12\n" +
                                      "  x += 34\n")
        self.assertEquals(UnitType, info.package.findFunction(name="f").returnType)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[0].body.statements[1]))

    def testAndExpr(self):
        source = "def f = true && false"
        info = self.analyzeFromSource(source)
        self.assertEquals(BooleanType, info.getType(info.ast.modules[0].definitions[0].body))

    def testOrExpr(self):
        source = "def f = true || false"
        info = self.analyzeFromSource(source)
        self.assertEquals(BooleanType, info.getType(info.ast.modules[0].definitions[0].body))

    def testOperatorFunctionExpr(self):
        source = "def @ (x: i64, y: i64) = x + y + 2\n" + \
                 "def f = 12 @ 34"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.getType(info.ast.modules[0].definitions[1].body))

    def testBinaryOperatorStaticMethodExpr(self):
        source = "class Foo\n" + \
                 "  static def @ (x: i64, y: i64) = x + y + 2\n" + \
                 "  def f = 12 @ 34"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="Foo.f")
        self.assertEquals(I64Type, f.returnType)

    def testBinaryOperatorNonStaticMethodExpr(self):
        source = "class Foo\n" + \
                 "  def @ (x: i64, y: i64) = x + y + 2\n" + \
                 "  def f = 12 @ 34"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="Foo.f")
        self.assertEquals(I64Type, f.returnType)

    def testBinaryOperatorClassExpr(self):
        source = "class @(x: i64, y: i64)\n" + \
                 "def f = 12 @ 34"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        At = info.package.findClass(name="@")
        self.assertEquals(ClassType(At), f.returnType)

    def testBinaryOperatorRightExpr(self):
        source = "def :: (x: i64, y: String) = 0\n" + \
                 "def f = 12 :: \"34\""
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testOperatorSubtypeAssignment(self):
        source = "def @ (x: Object, y: String): String = \"foo\"\n" + \
                 "def f =\n" + \
                 "  var x = Object()\n" + \
                 "  x @= \"bar\""
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        x = f.variables[0]
        self.assertEquals(getRootClassType(), x.type)
        self.assertEquals(UnitType, info.getType(f.astDefn.body.statements[1]))

    def testOperatorOtherTypeAssignment(self):
        source = "def @ (x: i64, y: i64): String = \"foo\"\n" + \
                 "def f =\n" + \
                 "  var x = 12\n" + \
                 "  x @= 34"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    @unittest.skip("need std integration or mocking")
    def testTupleExprNormal(self):
        # make sure primitive values are not allowed
        self.fail()

    def testTupleExprStd(self):
        source = TUPLE_SOURCE + \
                 "let g = \"foo\", \"bar\""
        info = self.analyzeFromSource(source, name=STD_NAME)
        tupleClass = info.package.findClass(name="Tuple2")
        g = info.package.findGlobal(name="g")
        self.assertEquals(ClassType(tupleClass, (getStringType(), getStringType())), g.type)

    def testTupleExprStdPrimitive(self):
        source = TUPLE_SOURCE + \
                 "let g = 1, 2"
        self.assertRaises(TypeException, self.analyzeFromSource, source, name=STD_NAME)

    def testTupleExprNoStd(self):
        self.assertRaises(ScopeException, self.analyzeFromSource, "let x = \"foo\", \"bar\"")

    def testIfExpr(self):
        source = "def f = if (true) 12 else 34"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.getType(info.ast.modules[0].definitions[0].body))

    def testIfExprNonBooleanCondition(self):
        source = "def f = if (-1) 12 else 34"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testIfExprNonCombineableBranches(self):
        source = "def f = if (true) false else 34"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testIfExprReturn(self):
        source = "def f = if (true) return 34 else 12"
        info = self.analyzeFromSource(source)
        self.assertEquals(I64Type, info.getType(info.ast.modules[0].definitions[0].body))

    def testIfExprWithoutElse(self):
        source = "def f = if (true) 12"
        info = self.analyzeFromSource(source)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[0].body))

    def testWhileExpr(self):
        source = "def f = while (true) 12"
        info = self.analyzeFromSource(source)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[0].body))

    def testMatchExprVarNoType(self):
        source = "def f(x: i64) = match (x)\n" + \
                 "  case y => y.to-string"
        info = self.analyzeFromSource(source)
        matchAst = info.ast.modules[0].definitions[0].body
        self.assertEquals(getStringType(), info.getType(matchAst))
        self.assertEquals(I64Type, info.getType(matchAst.matcher.cases[0].pattern))
        self.assertEquals(getStringType(), info.getType(matchAst.matcher.cases[0].expression))

    def testMatchExprVarWithType(self):
        source = "def f(x: i64) = match (x)\n" + \
                 "  case y: i64 => y"
        info = self.analyzeFromSource(source)
        matchAst = info.ast.modules[0].definitions[0].body
        self.assertEquals(I64Type, info.getType(matchAst))

    def testMatchExprVarWithCond(self):
        source = "def f(x: i64) = match (x)\n" + \
                 "  case y if x == 0 => y"
        info = self.analyzeFromSource(source)
        matchAst = info.ast.modules[0].definitions[0].body
        self.assertEquals(I64Type, info.getType(matchAst))
        self.assertEquals(BooleanType, info.getType(matchAst.matcher.cases[0].condition))
        self.assertEquals(I64Type, info.getType(matchAst.matcher.cases[0].expression))

    def testMatchExprVarWithBadCond(self):
        source = "def f(x: i64) = match (x)\n" + \
                 "  case y if x => y"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testMatchExprVarUntestable(self):
        source = "class Foo[static T]\n" + \
                 "def f(x: Object) =\n" + \
                 "  match (x)\n" + \
                 "    case foo: Foo[String] => 1"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testMatchExprVarExistentialTestable(self):
        source = "class Foo[static T]\n" + \
                 "def f(x: Object) =\n" + \
                 "  match (x)\n" + \
                 "    case foo: Foo[_] => 1"
        info = self.analyzeFromSource(source)
        matchAst = info.ast.modules[0].definitions[1].body.statements[0]
        ty = info.getType(matchAst.matcher.cases[0].pattern)
        self.assertTrue(isinstance(ty, ExistentialType))

    def testMatchExprVarShadow(self):
        source = "def f(x: Object) =\n" + \
                 "  let y = \"foo\"\n" + \
                 "  match (x)\n" + \
                 "    case y => y"
        info = self.analyzeFromSource(source)
        matchAst = info.ast.modules[0].definitions[0].body.statements[1]
        self.assertEquals(getStringType(), info.getType(matchAst))
        self.assertEquals(getStringType(), info.getType(matchAst.matcher.cases[0].pattern))
        self.assertEquals(getStringType(), info.getType(matchAst.matcher.cases[0].expression))

    def testMatchExprVarShadowWithType(self):
        source = "def f(x: Object) =\n" + \
                 "  let y = \"foo\"\n" + \
                 "  match (x)\n" + \
                 "    case y: Object => y"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testMatchExprBlankNoType(self):
        source = "def f(x: String) =\n" + \
                 "  match (x)\n" + \
                 "    case _ => x"
        info = self.analyzeFromSource(source)
        matchAst = info.ast.modules[0].definitions[0].body.statements[0]
        self.assertEquals(getStringType(), info.getType(matchAst))
        self.assertEquals(getStringType(), info.getType(matchAst.matcher.cases[0].pattern))

    def testMatchExprBlankWithType(self):
        source = "def f(x: String) =\n" + \
                 "  match (x)\n" + \
                 "    case _: Object => x"
        info = self.analyzeFromSource(source)
        matchAst = info.ast.modules[0].definitions[0].body.statements[0]
        self.assertEquals(getStringType(), info.getType(matchAst))
        self.assertEquals(getRootClassType(), info.getType(matchAst.matcher.cases[0].pattern))

    def testMatchExprIntLiteral(self):
        source = "def f =\n" + \
                 "  match (12)\n" + \
                 "    case 34 => 56"
        info = self.analyzeFromSource(source)
        matchAst = info.ast.modules[0].definitions[0].body.statements[0]
        self.assertEquals(I64Type, info.getType(matchAst))
        self.assertEquals(I64Type, info.getType(matchAst.matcher.cases[0].pattern))

    def testMatchExprTuple(self):
        source = TUPLE_SOURCE + \
                 "def f(x: Object) =\n" + \
                 "  match (x)\n" + \
                 "    case (y: String, z: String) => y"
        info = self.analyzeFromSource(source, name=STD_NAME)
        tupleClass = info.package.findClass(name="Tuple2")
        matchAst = info.ast.modules[0].definitions[1].body.statements[0]
        self.assertEquals(ClassType(tupleClass, (getStringType(), getStringType())),
                          info.getType(matchAst.matcher.cases[0].pattern))
        self.assertEquals(getStringType(),
                          info.getType(matchAst.matcher.cases[0].pattern.pattern.patterns[0]))
        self.assertEquals(getStringType(), info.getType(matchAst.matcher.cases[0].expression))

    def testMatchExprValue(self):
        foo = Package(name=Name(["foo"]))
        foo.addGlobal(Name(["bar"]), sourceName="bar",
                      type=I64Type, flags=frozenset([PUBLIC, LET]))
        source = "def f(x: i64) =\n" + \
                 "  match (x)\n" + \
                 "    case foo.bar => 1"
        info = self.analyzeFromSource(source, packageLoader=FakePackageLoader([foo]))
        matchAst = info.ast.modules[0].definitions[0].body.statements[0]
        self.assertEquals(I64Type, info.getType(matchAst.matcher.cases[0].pattern))

    def testMatchExprDestructureWithoutMatcher(self):
        source = "class Foo\n" + \
                 "def f(x: Object) =\n" + \
                 "  match (x)\n" + \
                 "    case Foo(_) => 12"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testMatchExprDestructureWithFunctionMatcher(self):
        source = OPTION_SOURCE + \
                 "class A\n" + \
                 "def Matcher(x: A): Option[String] = Some[String](\"matched\")\n" + \
                 "def f(x: A) =\n" + \
                 "  match (x)\n" + \
                 "    case Matcher(s) => s"
        info = self.analyzeFromSource(source, name=STD_NAME)
        A = info.package.findClass(name="A")
        f = info.package.findFunction(name="f")
        matchCase = info.ast.modules[0].definitions[-1].body.statements[0].matcher.cases[0]
        self.assertEquals(ClassType(A), info.getType(matchCase.pattern))
        self.assertEquals(getStringType(), info.getType(matchCase.pattern.patterns[0]))
        self.assertEquals(getStringType(), f.returnType)

    def testMatchExprDestructureWithFunctionMatcherTuple(self):
        source = OPTION_SOURCE + \
                 TUPLE_SOURCE + \
                 "def Matcher(x: Object): Option[(String, String)] = None\n" + \
                 "def f(x: Object) =\n" + \
                 "  match (x)\n" + \
                 "    case Matcher(a, b) => a"
        info = self.analyzeFromSource(source, name=STD_NAME)
        f = info.package.findFunction(name="f")
        tupleClass = info.package.findClass(name="Tuple2")
        matchCase = info.ast.modules[0].definitions[-1].body.statements[0].matcher.cases[0]
        self.assertEquals(getRootClassType(), info.getType(matchCase.pattern))
        self.assertEquals(getStringType(), info.getType(matchCase.pattern.patterns[0]))
        self.assertEquals(getStringType(), info.getType(matchCase.pattern.patterns[1]))
        self.assertEquals(getStringType(), f.returnType)

    def testMatchExprDestructureWithClosureMatcher(self):
        source = OPTION_SOURCE + \
                 "let Matcher = lambda (x: Object) None\n" + \
                 "def f(x: Object) =\n" + \
                 "  match (x)\n" + \
                 "    case Matcher(a) => a"
        info = self.analyzeFromSource(source, name=STD_NAME)
        Matcher = info.package.findGlobal(name="Matcher")
        call = info.package.findFunction(name=Name([LAMBDA_SUFFIX]))
        astDestructure = (
            info.ast.modules[0].definitions[-1].body.statements[0].matcher.cases[0].pattern)
        self.assertIs(Matcher.id, info.getUseInfo(astDestructure.prefix[0]).defnInfo.irDefn.id)
        self.assertIs(call.id, info.getUseInfo(astDestructure).defnInfo.irDefn.id)
        self.assertTrue(info.hasCallInfo(astDestructure))

    def testMatchExprDestructureWithBadMatcherFunctionArgs(self):
        source = OPTION_SOURCE + \
                 "def Matcher: Option[String] = Some[String](\"matched\")\n" + \
                 "def f(x: Object) =\n" + \
                 "  match (x)\n" + \
                 "    case Matcher(s) => s"
        self.assertRaises(TypeException, self.analyzeFromSource, source, name=STD_NAME)

    def testMatchExprDestructureWithMatcherStaticMethod(self):
        source = OPTION_SOURCE + \
                 "class Foo\n" + \
                 "  static def try-match(obj: Object) = None\n" + \
                 "def f(x: Object) =\n" + \
                 "  match (x)\n" + \
                 "    case Foo(a) => 12"
        info = self.analyzeFromSource(source, name=STD_NAME)
        matchCase = info.ast.modules[0].definitions[-1].body.statements[0].matcher.cases[0]
        self.assertEquals(getRootClassType(), info.getType(matchCase.pattern))
        self.assertEquals(getNothingClassType(), info.getType(matchCase.pattern.patterns[0]))

    def testMatchExprDestructureWithMethod(self):
        source = OPTION_SOURCE + \
                 "class Matcher\n" + \
                 "  def try-match(obj: Object) = None\n" + \
                 "def f(x: Object) =\n" + \
                 "  let m = Matcher()\n" + \
                 "  match (x)\n" + \
                 "    case m(a) => 12"
        info = self.analyzeFromSource(source, name=STD_NAME)
        matchCase = info.ast.modules[0].definitions[-1].body.statements[1].matcher.cases[0]
        self.assertEquals(getRootClassType(), info.getType(matchCase.pattern))
        self.assertEquals(getNothingClassType(), info.getType(matchCase.pattern.patterns[0]))

    def testMatchExprDestructureWithMethodInScope(self):
        source = OPTION_SOURCE + \
                 "class Foo[static T]\n" + \
                 "  def matcher(obj: T) = Some[T](obj)\n" + \
                 "  def f(obj: T) =\n" + \
                 "    match (obj)\n" + \
                 "      case matcher(x) => x"
        info = self.analyzeFromSource(source, name=STD_NAME)
        T = info.package.findTypeParameter(name="Foo.T")
        f = info.package.findFunction(name="Foo.f")
        matchCase = info.ast.modules[0].definitions[-1].members[1].body.statements[0].matcher.cases[0]
        self.assertEquals(VariableType(T), info.getType(matchCase.pattern))
        self.assertEquals(VariableType(T), info.getType(matchCase.pattern.patterns[0]))
        self.assertEquals(VariableType(T), f.returnType)

    def testMatchExprUnaryDestructure(self):
        source = OPTION_SOURCE + \
                 "def ~ (obj: Object) = Some[String](\"foo\")\n" + \
                 "def f(obj: Object) =\n" + \
                 "  match (obj)\n" + \
                 "    case ~s => s"
        info = self.analyzeFromSource(source, name=STD_NAME)
        matchCase = info.ast.modules[0].definitions[-1].body.statements[0].matcher.cases[0]
        self.assertEquals(getRootClassType(), info.getType(matchCase.pattern))
        self.assertEquals(getStringType(), info.getType(matchCase.pattern.pattern))

    def testMatchExprBinaryLeftDestructure(self):
        source = OPTION_SOURCE + \
                 TUPLE_SOURCE + \
                 "class Foo\n" + \
                 "class Bar\n" + \
                 "def @ (obj: Object) = Some[(Foo, Bar)]((Foo(), Bar()))\n" + \
                 "def f(obj: Object) =\n" + \
                 "  match (obj)\n" + \
                 "    case a @ b => ()"
        info = self.analyzeFromSource(source, name=STD_NAME)
        Foo = info.package.findClass(name="Foo")
        Bar = info.package.findClass(name="Bar")
        matchCase = info.ast.modules[0].definitions[-1].body.statements[0].matcher.cases[0]
        self.assertEquals(getRootClassType(), info.getType(matchCase.pattern))
        self.assertEquals(ClassType(Foo), info.getType(matchCase.pattern.left))
        self.assertEquals(ClassType(Bar), info.getType(matchCase.pattern.right))

    def testMatchExprBinaryRightDestructure(self):
        source = OPTION_SOURCE + \
                 TUPLE_SOURCE + \
                 "class Foo\n" + \
                 "class Bar\n" + \
                 "def :: (obj: Object) = Some[(Foo, Bar)]((Foo(), Bar()))\n" + \
                 "def f(obj: Object) =\n" + \
                 "  match (obj)\n" + \
                 "    case a :: b => ()"
        info = self.analyzeFromSource(source, name=STD_NAME)
        Foo = info.package.findClass(name="Foo")
        Bar = info.package.findClass(name="Bar")
        matchCase = info.ast.modules[0].definitions[-1].body.statements[0].matcher.cases[0]
        self.assertEquals(getRootClassType(), info.getType(matchCase.pattern))
        self.assertEquals(ClassType(Foo), info.getType(matchCase.pattern.left))
        self.assertEquals(ClassType(Bar), info.getType(matchCase.pattern.right))

    def testMatchExprDisjointType(self):
        source = "class Foo\n" + \
                 "class Bar\n" + \
                 "def f(foo: Foo) =\n" + \
                 "  match (foo)\n" + \
                 "    case _: Bar => ()"
        info = self.analyzeFromSource(source)
        # pass if no error

    def testMatchExprTestStaticAndDynamic(self):
        source = OPTION_SOURCE + \
                 "class Box[static +T]\n" + \
                 "class FullBox[static +T](value: T) <: Box[T]\n" + \
                 "  static def try-match(box: Box[T]): Option[T] =\n" + \
                 "    match (box)\n" + \
                 "      case full-box: FullBox[T] => Some[T](full-box.value)\n" + \
                 "      case _ => None"
        info = self.analyzeFromSource(source, name=STD_NAME)
        T = info.package.findClass(name="FullBox").typeParameters[0]
        TType = VariableType(T)
        Some = info.package.findClass(name="Some")
        SomeTType = ClassType(Some, (TType,))
        tryMatch = info.package.findFunction(name="FullBox.try-match")
        caseType = info.getType(tryMatch.astDefn.body.statements[0].matcher.cases[0].expression)
        self.assertEquals(SomeTType, caseType)

    def testMatchExprTestStaticAndDynamicTwoParamsFail(self):
        source = OPTION_SOURCE + \
                 "class Box[static +T]\n" + \
                 "class MoreBox[static +S, static +T](foo: S, bar: T) <: Box[T]\n" + \
                 "  static def try-match(box: Box[T]): Option[T] =\n" + \
                 "    match (box)\n" + \
                 "      case more-box: MoreBox[String, T] => Some[T](more-box.bar)\n" + \
                 "      case _ => None"
        self.assertRaises(TypeException, self.analyzeFromSource, source, name=STD_NAME)

    def testMatchExprTestStaticAndDynamicTwoParamsOk(self):
        source = OPTION_SOURCE + \
                 "class Box[static +T]\n" + \
                 "class MoreBox[static +S, static +T](foo: S, bar: T) <: Box[T]\n" + \
                 "  static def try-match(box: Box[T]): Option[T] =\n" + \
                 "    match (box)\n" + \
                 "      case more-box: MoreBox[_, T] => Some[T](more-box.bar)\n" + \
                 "      case _ => None"
        info = self.analyzeFromSource(source, name=STD_NAME)
        T = info.package.findTypeParameter(name="MoreBox.T")
        tryMatchAst = info.package.findFunction(name="MoreBox.try-match").astDefn
        resultAst = tryMatchAst.body.statements[0].matcher.cases[0].expression.arguments[0]
        resultType = info.getType(resultAst)
        self.assertEquals(VariableType(T), resultType)

    def testMatchExprTestStaticAndDynamicTypeParameterUpperBound(self):
        source = "class Box[static +T]\n" + \
                 "class FullBox[static +T](value: T) <: Box[T]\n" + \
                 "def f[static T <: Box[String]](box: T) =\n" + \
                 "  match (box)\n" + \
                 "    case full-box: FullBox[String] => full-box.value"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(getStringType(), f.returnType)

    def testMatchExprTestStaticAndDynamicExistential(self):
        source = "class Box[static +T]\n" + \
                 "class FullBox[static +T](value: T) <: Box[T]\n" + \
                 "def f(box: forsome [X] Box[String]) =\n" + \
                 "  match (box)\n" + \
                 "    case full-box: FullBox[String] => full-box.value"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(getStringType(), f.returnType)

    def testMatchExprTestStaticAndDynamicResultFail(self):
        source = OPTION_SOURCE + \
                 "class Result[static +V, static +E]\n" + \
                 "class Ok[static +V](value: V) <: Result[V, Nothing]\n" + \
                 "  static def try-match(result: Result[V, Object]) =\n" + \
                 "    match (result)\n" + \
                 "      case ok: Ok[V] => Some[V](ok.value)\n" + \
                 "      case _ => None\n" + \
                 "class Err[static +E](error: E) <: Result[Nothing, E]\n" + \
                 "  static def try-match(result: Result[Object, E]) =\n" + \
                 "    match (result)\n" + \
                 "      case err: Err[E] => Some[E](err.error)\n" + \
                 "      case _ => None"
        self.assertRaises(TypeException, self.analyzeFromSource, source, name=STD_NAME)

    def testMatchExprTestStaticAndDynamicResultOk(self):
        source = OPTION_SOURCE + \
                 "class Result[static +V, static +E]\n" + \
                 "class Ok[static +V](value: V) <: Result[V, Nothing]\n" + \
                 "  static def try-match(result: Result[V, _]) =\n" + \
                 "    match (result)\n" + \
                 "      case ok: Ok[V] => Some[V](ok.value)\n" + \
                 "      case _ => None"
        info = self.analyzeFromSource(source, name=STD_NAME)
        V = info.package.findTypeParameter(name="Ok.V")
        Option = info.package.findClass(name="Option")
        tryMatch = info.package.findFunction(name="Ok.try-match")
        self.assertEquals(ClassType(Option, (VariableType(V),)), tryMatch.returnType)

    def testMatchExprTestStaticAndDynamicBounds(self):
        source = "class Foo\n" + \
                 "class Box[static +T]\n" + \
                 "class FooBox[static +T <: Foo] <: Box[T]\n" + \
                 "def f(box: Box[Object]) =\n" + \
                 "  match (box)\n" + \
                 "    case foo-box: FooBox[Foo] => ()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testMatchExprTestStaticAndDynamicOption(self):
        source = OPTION_SOURCE + \
                 "class Foo[static F]\n" + \
                 "class Bar[static B] <: Foo[Option[B]]\n" + \
                 "def f(foo: Foo[Option[String]]) =\n" + \
                 "  match (foo)\n" + \
                 "    case bar: Bar[String] => true\n" + \
                 "    case _ => false"
        self.analyzeFromSource(source, name=STD_NAME)
        # pass if no exception is raised

    def testMatchExprTestStaticAndDynamicNothingStatic(self):
        source = "def f(nothing: Nothing) =\n" + \
                 "  match (nothing)\n" + \
                 "    case s: String => s"
        self.analyzeFromSource(source)
        # pass if no exception is raised

    def testMatchExprTestStaticAndDynamicNothingTest(self):
        source = "def f(obj: Object) =\n" + \
                 "  match (obj)\n" + \
                 "    case n: Nothing => n"
        self.analyzeFromSource(source)
        # pass if no exception is raised

    def testThrowExpr(self):
        source = "def f(exn: Exception) = throw exn"
        info = self.analyzeFromSource(source)
        self.assertEquals(ClassType(getNothingClass()),
                          info.package.findFunction(name="f").returnType)
        self.assertEquals(NoType, info.getType(info.ast.modules[0].definitions[0].body))

    def testThrowNonException(self):
        self.assertRaises(TypeException, self.analyzeFromSource, "def f = throw 12")

    def testThrowInIfCondition(self):
        source = "def f(exn: Exception) = if (throw exn) 12"
        info = self.analyzeFromSource(source)
        self.assertEquals(NoType, info.getType(info.ast.modules[0].definitions[0].body.condition))

    def testThrowInWhileCondition(self):
        source = "def f(exn: Exception) = while (throw exn) ()"
        info = self.analyzeFromSource(source)
        self.assertEquals(NoType, info.getType(info.ast.modules[0].definitions[0].body.condition))

    def testTryExpr(self):
        source = "class Base\n" + \
                 "class A <: Base\n" + \
                 "  def this = ()\n" + \
                 "class B <: Base\n" + \
                 "  def this = ()\n" + \
                 "def f = try A() catch (exn) B() finally 12"
        info = self.analyzeFromSource(source)
        baseTy = ClassType(info.package.findClass(name="Base"), ())
        astBody = info.ast.modules[0].definitions[3].body
        self.assertEquals(baseTy, info.getType(astBody))
        self.assertEquals(ClassType(getExceptionClass()),
                          info.getType(astBody.catchHandler.cases[0].pattern))
        self.assertEquals(I64Type, info.getType(astBody.finallyHandler))

    def testTryCombineBadCatch(self):
        self.assertRaises(TypeException, self.analyzeFromSource,
                          "def f = try 12 catch\n" +
                          "    case exn => exn")

    def testTryBadCondition(self):
        self.assertRaises(TypeException, self.analyzeFromSource,
                          "def f = try 12 catch\n" +
                          "  case exn if 34 => 56")

    def testTryCatchSubtype(self):
        source = "class Foo <: Exception\n" + \
                 "def f = try 12 catch (exn: Foo) 34"
        info = self.analyzeFromSource(source)
        exnClass = info.package.findClass(name="Foo")
        exnTy = info.getType(info.ast.modules[0].definitions[1].body.catchHandler.cases[0].pattern)
        self.assertIs(exnClass, exnTy.clas)
        self.assertIs(exnClass, info.package.findFunction(name="f").variables[0].type.clas)

    def testTryCatchUntestable(self):
        source = "class E[static T] <: Exception\n" + \
                 "def f =\n" + \
                 "  try\n" + \
                 "    0\n" + \
                 "  catch (x: E[String]) 1"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testWhileExprNonBooleanCondition(self):
        self.assertRaises(TypeException, self.analyzeFromSource, "def f = while (-1) 12")

    def testLambdaExpressionPrimitive(self):
        source = "let f = lambda (x: i32) x"
        info = self.analyzeFromSource(source)
        astLambda = info.ast.modules[0].definitions[0].expression
        irFunction = info.getDefnInfo(astLambda).irDefn
        irClosureClass = info.getClosureInfo(astLambda).irClosureClass
        lambdaType = ClassType.forReceiver(irClosureClass)
        self.assertEquals(
            self.makeFunction(
                Name([LAMBDA_SUFFIX]),
                typeParameters=[],
                returnType=I32Type,
                parameterTypes=[lambdaType, I32Type]),
            irFunction)
        self.assertEquals(lambdaType, info.getType(astLambda))

    def testLambdaExpressionPrimitiveCapture(self):
        source = "def add(x: i32) = lambda (y: i32) x + y"
        info = self.analyzeFromSource(source)
        astLambda = info.ast.modules[0].definitions[0].body
        irFunction = info.getDefnInfo(astLambda).irDefn
        irClosureClass = info.getClosureInfo(astLambda).irClosureClass
        lambdaType = ClassType.forReceiver(irClosureClass)
        self.assertEquals(
            self.makeFunction(
                Name(["add", LAMBDA_SUFFIX]),
                typeParameters=[],
                returnType=I32Type,
                parameterTypes=[lambdaType, I32Type]),
            irFunction)
        self.assertEquals(
            self.makeVariable(
                Name(["add", LAMBDA_SUFFIX, RECEIVER_SUFFIX]),
                type=lambdaType, kind=PARAMETER, flags=frozenset([LET])),
            irFunction.variables[0])
        self.assertEquals(lambdaType, info.getType(astLambda))

    def testLambdaExpressionObject(self):
        source = FUNCTION_SOURCE + \
                 "let f = lambda (o: Object) o.to-string"
        info = self.analyzeFromSource(source, name=STD_NAME)
        astLambda = info.ast.modules[0].definitions[-1].expression
        irFunction = info.getDefnInfo(astLambda).irDefn
        irClosureClass = info.getClosureInfo(astLambda).irClosureClass
        lambdaType = ClassType.forReceiver(irClosureClass)
        self.assertEquals(
            self.makeFunction(
                Name([LAMBDA_SUFFIX]),
                typeParameters=[],
                returnType=getStringType(),
                parameterTypes=[lambdaType, getRootClassType()]),
            irFunction)
        self.assertEquals(lambdaType, info.getType(astLambda))
        functionTrait = info.package.findTrait(name="Function1")
        functionType = ClassType(functionTrait, (getStringType(), getRootClassType()))
        self.assertTrue(lambdaType.isSubtypeOf(functionType))

    def testLambdaExpressionParameterized(self):
        source = FUNCTION_SOURCE + \
                 "def f[static T] = lambda (x: T) x\n" + \
                 "let g = f[String]"
        info = self.analyzeFromSource(source, name=STD_NAME)
        astLambda = info.ast.modules[0].definitions[-2].body
        T = info.package.findTypeParameter(name="f.T")
        TType = VariableType(T)
        irFunction = info.getDefnInfo(astLambda).irDefn
        irClosureClass = info.getClosureInfo(astLambda).irClosureClass
        lambdaType = ClassType.forReceiver(irClosureClass)
        self.assertEquals(
            self.makeFunction(
                Name(["f", LAMBDA_SUFFIX]),
                typeParameters=[T],
                returnType=TType,
                parameterTypes=[lambdaType, TType]),
            irFunction)
        functionTrait = info.package.findTrait(name="Function1")
        parameterizedFunctionType = ClassType(functionTrait, (TType, TType))
        self.assertTrue(lambdaType.isSubtypeOf(parameterizedFunctionType))
        specializedFunctionType = ClassType(functionTrait, (getStringType(), getStringType()))
        g = info.package.findGlobal(name="g")
        self.assertTrue(g.type.isSubtypeOf(specializedFunctionType))

    def testLambdaExpressionFunctionType(self):
        source = FUNCTION_SOURCE + \
                 "let g: String -> Object = lambda (x: String) x"
        self.analyzeFromSource(source, name=STD_NAME)
        # pass if no error

    def testReturnExpression(self):
        source = "def f = return 12"
        info = self.analyzeFromSource(source)
        self.assertEquals(NoType, info.getType(info.ast.modules[0].definitions[0].body))
        self.assertEquals(I64Type, info.package.findFunction(name="f").returnType)

    def testReturnExpressionInGlobal(self):
        source = "var g = return 12"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testReturnExpressionInClass(self):
        source = "class C\n" + \
                 "  var x = return 12"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testReturnEmpty(self):
        source = "def f = return"
        info = self.analyzeFromSource(source)
        self.assertEquals(NoType, info.getType(info.ast.modules[0].definitions[0].body))
        self.assertEquals(UnitType, info.package.findFunction(name="f").returnType)

    def testConstructRootClass(self):
        source = "def f = Object()"
        info = self.analyzeFromSource(source)
        rootClass = getRootClass()
        self.assertEquals(ClassType(rootClass, ()), info.getType(info.ast.modules[0].definitions[0].body))

    def testExistentialLoadVar(self):
        source = "class Foo\n" + \
                 "  let foof = 12\n" + \
                 "class Bar[static T] <: Foo\n" + \
                 "def f(bar: forsome [X] Bar[X]) = bar.foof"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testExistentialLoadPlain(self):
        source = "class Box[static T](value: i64)\n" + \
                 "def f(box: forsome [X] Box[X]) = box.value"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testExistentialCallVar(self):
        source = "class Foo\n" + \
                 "  def foom = 12\n" + \
                 "class Bar[static T] <: Foo\n" + \
                 "def f(bar: forsome [X] Bar[X]) = bar.foom"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testExistentialCallPlain(self):
        source = "class Box[static T]\n" + \
                 "  def get = 12\n" + \
                 "def f(box: forsome [X] Box[X]) = box.get"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testExistentialStoreVar(self):
        source = "class Box[static T](value: T)\n" + \
                 "def f(box: forsome [X] Box[X]) =\n" + \
                 "  box.value = Object()\n" + \
                 "  ()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testExistentialStorePlain(self):
        source = "class Box[static T]\n" + \
                 "  var value: i64\n" + \
                 "def f(box: forsome [X] Box[X]) =\n" + \
                 "  box.value = 12\n" + \
                 "  ()"
        self.analyzeFromSource(source)
        # pass if no error

    def testExistentialCallValue(self):
        source = FUNCTION_SOURCE + \
                 "def f(g: forsome [R <: String, P >: String] Function1[R, P]) =\n" + \
                 "  (g)(\"foo\")"
        info = self.analyzeFromSource(source)
        self.assertEquals(getStringType(), info.package.findFunction(name="f").returnType)

    def testDestructureMatchOnExistentialValue(self):
        source = OPTION_SOURCE + \
                 "def match-fn(obj: Object): Option[String] = None\n" + \
                 "def f(x: forsome [X] X) =\n" + \
                 "  match (x)\n" + \
                 "    case match-fn(s) => s\n" + \
                 "    case _ => \"nothing\""
        self.analyzeFromSource(source, name=STD_NAME)
        # pass if no errors

    def testDestructureMatchWithExplicitExistentialMatcher(self):
        source = OPTION_SOURCE + \
                 "class Matcher[static T]\n" + \
                 "  def try-match(obj: Object): Option[String] = None\n" + \
                 "def f(x: Object, m: forsome [X] Matcher[X]) =\n" + \
                 "  match (x)\n" + \
                 "    case m.try-match(s) => s\n" + \
                 "    case _ => \"nothing\""
        self.analyzeFromSource(source, name=STD_NAME)
        # pass if no errors

    def testDestructureWithImplicitExistentialMatcher(self):
        source = OPTION_SOURCE + \
                 "class Matcher[static T]\n" + \
                 "  def try-match(obj: Object): Option[String] = None\n" + \
                 "def f(x: Object, m: forsome [X] Matcher[X]) =\n" + \
                 "  match (x)\n" + \
                 "    case m(s) => s\n" + \
                 "    case _ => \"nothing\""
        self.analyzeFromSource(source, name=STD_NAME)
        # pass if no errors

    def testMoveExistentialListOfBoxes(self):
        source = "abstract class List[static T]\n" + \
                 "  abstract def get(i: i64): T\n" + \
                 "class Box[static T](value: T)\n" + \
                 "def f(list: forsome [X] List[Box[X]]) =\n" + \
                 "  list.get(0).value = list.get(1).value"
        self.assertRaises(ScopeException, self.analyzeFromSource, source)
        # This is technically safe, but we don't want the compiler to have to prove it. In
        # Java, this would be done with a helper method with wildcard capture. We'll have
        # something like that or an open expression in the future.

    def testMoveListOfExistentialBoxes(self):
        source = "abstract class List[static T]\n" + \
                 "  abstract def get(i: i64): T\n" + \
                 "class Box[static T](value: T)\n" + \
                 "def f(list: List[forsome [X] Box[X]]) =\n" + \
                 "  list.get(0).value = list.get(1).value"
        self.assertRaises(TypeException, self.analyzeFromSource, source)
        # This is definitely not safe.

    # Types
    def testUnitType(self):
        source = "var g: unit"
        info = self.analyzeFromSource(source)
        self.assertEquals(UnitType, info.package.findGlobal(name="g").type)

    def testI32Type(self):
        source = "var g: i32"
        info = self.analyzeFromSource(source)
        self.assertEquals(I32Type, info.package.findGlobal(name="g").type)

    def testF32Type(self):
        source = "var g: f32"
        info = self.analyzeFromSource(source)
        self.assertEquals(F32Type, info.package.findGlobal(name="g").type)

    def testBooleanType(self):
        source = "var g: boolean"
        info = self.analyzeFromSource(source)
        self.assertEquals(BooleanType, info.package.findGlobal(name="g").type)

    def testRootClassType(self):
        source = "var g: Object"
        info = self.analyzeFromSource(source)
        rootClass = getRootClass()
        self.assertEquals(ClassType(rootClass, ()), info.package.findGlobal(name="g").type)

    def testNullableClassType(self):
        source = "var g: Object?"
        info = self.analyzeFromSource(source)
        expected = ClassType(getRootClass(), (), frozenset([NULLABLE_TYPE_FLAG]))
        self.assertEquals(expected, info.package.findGlobal(name="g").type)

    def testNullableVariableType(self):
        source = "def f[static T](x: T?) = x"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        T = f.typeParameters[0]
        expected = VariableType(T, frozenset([NULLABLE_TYPE_FLAG]))
        self.assertEquals(expected, f.returnType)

    def testCallBuiltin(self):
        source = "def f = print(\"foo\")"
        info = self.analyzeFromSource(source)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[0].body))

    def testForeignProjectedClassType(self):
        package = Package(name=Name(["foo"]))
        clas = package.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                supertypes=[getRootClassType()],
                                constructors=[], fields=[],
                                methods=[], flags=frozenset([PUBLIC]))
        loader = FakePackageLoader([package])
        source = "var g: foo.Bar"
        info = self.analyzeFromSource(source, packageLoader=loader)
        expectedType = ClassType(clas)
        g = info.package.findGlobal(name="g")
        self.assertEquals(expectedType, g.type)

    def testForeignProjectedPackageType(self):
        loader = FakePackageLoader([Name(["foo", "bar"])])
        source = "var g: foo.bar"
        self.assertRaises(TypeException, self.analyzeFromSource, source, packageLoader=loader)

    def testForeignProjectedClassTypeWithPackageTypeArgs(self):
        package = Package(name=Name(["foo"]))
        clas = package.addClass(Name(["Bar"]), typeParameters=[],
                                supertypes=[getRootClassType()],
                                constructors=[], fields=[],
                                methods=[], flags=frozenset([PUBLIC]))
        loader = FakePackageLoader([package])
        source = "var g: foo[String].Bar"
        self.assertRaises(TypeException, self.analyzeFromSource, source, packageLoader=loader)

    def testForeignProjectedClassTypeWithTypeArgs(self):
        package = Package(name=Name(["foo"]))
        clas = package.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                supertypes=[getRootClassType()],
                                constructors=[], fields=[], methods=[],
                                flags=frozenset([PUBLIC]))
        package.addTypeParameter(clas, Name(["Bar", "T"]),
                                 upperBound=getRootClassType(),
                                 lowerBound=getNothingClassType(),
                                 flags=frozenset([STATIC]))
        loader = FakePackageLoader([package])

        source = "var g: foo.Bar[String]"
        info = self.analyzeFromSource(source, packageLoader=loader)
        expectedType = ClassType(clas, (getStringType(),))
        g = info.package.findGlobal(name="g")
        self.assertEquals(expectedType, g.type)

    def testForeignProjectedClassTypeWithTypeArgsOutOfBounds(self):
        package = Package(name=Name(["foo"]))
        clas = package.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                                supertypes=[getRootClassType()],
                                constructors=[], fields=[],
                                methods=[], flags=frozenset([PUBLIC]))
        package.addTypeParameter(clas, Name(["Bar", "T"]), upperBound=getStringType(),
                                 lowerBound=getNothingClassType(),
                                 flags=frozenset([STATIC]))
        loader = FakePackageLoader([package])
        source = "var g: foo.Bar[Object]"
        self.assertRaises(TypeException, self.analyzeFromSource, source, packageLoader=loader)

    def testTupleTypeNoStd(self):
        source = "var g: (Object, Object)"
        self.assertRaises(ScopeException, self.analyzeFromSource, source)

    def testTupleTypeStd(self):
        source = TUPLE_SOURCE + \
                 "var g: (Object, Object)?"
        info = self.analyzeFromSource(source, name=STD_NAME)
        ty = info.package.findGlobal(name="g").type
        tupleClass = info.package.findClass(name="Tuple2")
        expected = ClassType(tupleClass, (getRootClassType(), getRootClassType()),
                             frozenset([NULLABLE_TYPE_FLAG]))
        self.assertEquals(expected, ty)

    def testTupleTypePrimitive(self):
        source = TUPLE_SOURCE + \
                 "var g: (i64, i64)"
        self.assertRaises(TypeException, self.analyzeFromSource, source, name=STD_NAME)

    def testBlankTypeClassArg(self):
        source = "class Foo[static T <: String]\n" + \
                 "var g: Foo[_]"
        info = self.analyzeFromSource(source)
        ty = info.package.findGlobal(name="g").type
        Foo = info.package.findClass(name="Foo")
        blankAst = info.ast.modules[0].definitions[1].pattern.ty.typeArguments[0]
        X = info.getDefnInfo(blankAst).irDefn
        self.assertEquals(getStringType(), X.upperBound)
        self.assertIs(blankAst, X.astDefn)
        expected = ExistentialType((X,), ClassType(Foo, (VariableType(X),)))
        self.assertEquals(expected, ty)

    def testBlankTupleTypeArg(self):
        source = TUPLE_SOURCE + \
                 "var g: (_, _)"
        info = self.analyzeFromSource(source, name=STD_NAME)
        ty = info.package.findGlobal(name="g").type
        Tuple2 = info.package.findClass(name="Tuple2")
        tupleAst = info.ast.modules[0].definitions[-1].pattern.ty
        X = info.getDefnInfo(tupleAst.types[0]).irDefn
        Y = info.getDefnInfo(tupleAst.types[1]).irDefn
        expected = ExistentialType((X, Y),
                                   ClassType(Tuple2, (VariableType(X), VariableType(Y))))
        self.assertEquals(expected, ty)

    def testExistentialType(self):
        source = "let g: forsome [X] X?"
        info = self.analyzeFromSource(source)
        ty = info.package.findGlobal(name="g").type
        X = info.package.findTypeParameter(name=Name([EXISTENTIAL_SUFFIX, "X"]))
        expected = ExistentialType((X,), VariableType(X, frozenset([NULLABLE_TYPE_FLAG])))
        self.assertEquals(expected, ty)
        self.assertTrue(ty.isNullable())

    def testFunctionType(self):
        source = FUNCTION_SOURCE + \
                 "let g: String -> Object"
        info = self.analyzeFromSource(source, name=STD_NAME)
        ty = info.package.findGlobal(name="g").type
        fnTrait = info.package.findTrait(name="Function1")
        self.assertEquals(ClassType(fnTrait, (getRootClassType(), getStringType())), ty)

    def testFunctionTypePrimitive(self):
        source = FUNCTION_SOURCE + \
                 "let g: i32 -> boolean"
        self.assertRaises(TypeException, self.analyzeFromSource, source, name=STD_NAME)

    # Closures
    def testFunctionContextFields(self):
        source = "def f(x: i32) =\n" + \
                 "  def g = x\n" + \
                 "  g"
        info = self.analyzeFromSource(source)
        self.assertEquals(I32Type,
                          info.getType(info.ast.modules[0].definitions[0].body.statements[0].body))
        self.assertEquals(I32Type, info.getType(info.ast.modules[0].definitions[0].body.statements[1]))
        self.assertEquals(I32Type, info.package.findFunction(name="f").returnType)
        self.assertEquals(I32Type, info.package.findFunction(name="f.g").returnType)

    # Inheritance
    def testSupertypes(self):
        source = "class Foo\n" + \
                 "class Bar <: Foo"
        info = self.analyzeFromSource(source)
        fooClass = info.package.findClass(name="Foo")
        self.assertEquals([ClassType(getRootClass(), ())], fooClass.supertypes)
        barClass = info.package.findClass(name="Bar")
        self.assertEquals([ClassType(fooClass, ())] + fooClass.supertypes, barClass.supertypes)

    def testNullableSupertype(self):
        source = "class Foo <: Object?"
        self.assertRaises(InheritanceException, self.analyzeFromSource, source)

    def testNullableBounds(self):
        upperSource = "class Foo[static T <: Object?]"
        self.assertRaises(TypeException, self.analyzeFromSource, upperSource)
        lowerSource = "class Bar[static T >: Nothing?]"
        self.assertRaises(TypeException, self.analyzeFromSource, lowerSource)

    def testPrimitiveBounds(self):
        source = "class Foo[static T <: i64]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testExistentialBounds(self):
        source = "class Foo[static T <: forsome [X] X]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCallWithSubtype(self):
        source = "class Foo\n" + \
                 "class Bar <: Foo\n" + \
                 "def f(foo: Foo) = foo\n" + \
                 "def g(bar: Bar) =\n" + \
                 "  var x = f(bar)"
        info = self.analyzeFromSource(source)
        fooClass = info.package.findClass(name="Foo")
        barClass = info.package.findClass(name="Bar")
        astCall = info.ast.modules[0].definitions[3].body.statements[0].expression
        self.assertEquals(ClassType(barClass, ()), info.getType(astCall.arguments[0]))
        self.assertEquals(ClassType(fooClass, ()), info.getType(astCall))

    def testCallWithExistentialSubtype(self):
        source = "class Box[static T]\n" + \
                 "def f(box: forsome [X] Box[X]) = ()\n" + \
                 "def g = f(Box[Object]())"
        info = self.analyzeFromSource(source)
        Box = info.package.findClass(name="Box")
        X = info.package.findTypeParameter(name=Name(["f", EXISTENTIAL_SUFFIX, "X"]))
        f = info.package.findFunction(name="f")
        self.assertEquals(ExistentialType((X,), ClassType(Box, (VariableType(X),))),
                          f.parameterTypes[0])
        argType = info.getType(info.ast.modules[0].definitions[2].body.arguments[0])
        self.assertEquals(ClassType(Box, (getRootClassType(),)), argType)
        self.assertTrue(argType.isSubtypeOf(f.parameterTypes[0]))

    def testFunctionReturnBodyWithSubtype(self):
        source = "class Foo\n" + \
                 "class Bar <: Foo\n" + \
                 "def f(bar: Bar): Foo = bar"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        fooClass = info.package.findClass(name="Foo")
        barClass = info.package.findClass(name="Bar")
        self.assertEquals(ClassType(fooClass, ()), f.returnType)
        self.assertEquals(ClassType(barClass, ()), info.getType(info.ast.modules[0].definitions[2].body))

    def testFunctionReturnStatementWithSubtype(self):
        source = "class Foo\n" + \
                 "class Bar <: Foo\n" + \
                 "def f(bar: Bar): Foo = return bar"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        fooClass = info.package.findClass(name="Foo")
        barClass = info.package.findClass(name="Bar")
        self.assertEquals(ClassType(fooClass, ()), f.returnType)

    def testLoadInheritedParameterizedField(self):
        source = "class Foo[static +S](value: S)\n" + \
                 "class Bar[static +T] <: Foo[T]\n" + \
                 "  def this(value: T) = super(value)\n" + \
                 "  def get = value"
        info = self.analyzeFromSource(source)
        T = info.package.findTypeParameter(name="Bar.T")
        TType = VariableType(T)
        get = info.package.findFunction(name="Bar.get")
        self.assertEquals(TType, get.returnType)

    def testLoadInheritedParameterizedFieldFromTypeParameter(self):
        source = "class Foo[static +S](value: S)\n" + \
                 "class Bar[static +T] <: Foo[T]\n" + \
                 "  def this(value: T) = super(value)\n" + \
                 "def f[static U <: Bar[String]](obj: U) = obj.value"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(getStringType(), f.returnType)

    def testLoadInheritedParameterizedFieldFromExistential(self):
        source = "class Foo[static +S](value: S)\n" + \
                 "class Bar[static +T] <: Foo[T]\n" + \
                 "  def this(value: T) = super(value)\n" + \
                 "def f(obj: forsome [X] Bar[X]) = obj.value"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(getRootClassType(), f.returnType)

    def testCallInheritedMethod(self):
        source = "class Foo\n" + \
                 "  def m = 12\n" + \
                 "class Bar <: Foo\n" + \
                 "def f(bar: Bar) = bar.m"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testSimpleOverride(self):
        source = "class A\n" + \
                 "class Foo\n" + \
                 "  def m(a: A) = a\n" + \
                 "class Bar\n" + \
                 "  def m(a: A) = a"
        info = self.analyzeFromSource(source)
        fooClass = info.package.findClass(name="Foo")
        barClass = info.package.findClass(name="Bar")
        self.assertEquals(len(fooClass.methods), len(barClass.methods))
        self.assertIs(barClass, barClass.methods[-1].definingClass)

    def testBuiltinOverride(self):
        source = "def f = \"foo\".to-string"
        info = self.analyzeFromSource(source)
        useInfo = info.getUseInfo(info.ast.modules[0].definitions[0].body)
        receiverClass = useInfo.defnInfo.irDefn.definingClass
        self.assertIs(getStringClass(), receiverClass)

    def testRecursiveOverrideBuiltinWithoutReturnType(self):
        source = "class List(value: String, next: List?)\n" + \
                 "  override def to-string = value + if (next !== null) next.to-string else \"\""
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testRecursiveOverrideBuiltin(self):
        source = "class List(value: String, next: List?)\n" + \
                 "  override def to-string: String = value + if (next !== null) next.to-string else \"\""
        info = self.analyzeFromSource(source)
        List = info.package.findClass(name="List")
        useInfo = info.getUseInfo(info.ast.modules[0].definitions[0].members[0].body.right.trueExpr)
        receiverClass = useInfo.defnInfo.irDefn.definingClass
        self.assertIs(List, receiverClass)

    def testOverrideWithImplicitTypeParameters(self):
        source = "class A[static T]\n" + \
                 "  override def to-string = \"A\""
        info = self.analyzeFromSource(source)
        A = info.package.findClass(name="A")
        toString = A.findMethodBySourceName("to-string")
        self.assertIs(A, toString.definingClass)
        self.assertEquals([getRootClass().findMethodBySourceName("to-string").id],
                          [o.id for o in toString.overrides])

    def testOverrideCovariantParameters(self):
        source = "class A\n" + \
                 "class B <: A\n" + \
                 "class Foo\n" + \
                 "  def m(b: B) = this\n" + \
                 "class Bar <: Foo\n" + \
                 "  override def m(a: A) = this"
        info = self.analyzeFromSource(source)
        fooClass = info.package.findClass(name="Foo")
        barClass = info.package.findClass(name="Bar")
        self.assertEquals(len(fooClass.methods), len(barClass.methods))
        self.assertEquals([fooClass.methods[-1].id],
                          [o.id for o in barClass.methods[-1].overrides])

    def testOverrideContravariantReturn(self):
        source = "class A\n" + \
                 "  def this = ()\n" + \
                 "class B <: A\n" + \
                 "  def this = ()\n" + \
                 "class Foo\n" + \
                 "  def m = A()\n" + \
                 "class Bar <: Foo\n" + \
                 "  override def m = B()"
        info = self.analyzeFromSource(source)
        fooClass = info.package.findClass(name="Foo")
        barClass = info.package.findClass(name="Bar")
        self.assertEquals([fooClass.methods[-1].id],
                          [o.id for o in barClass.methods[-1].overrides])

    def testAmbiguousOverloadWithoutCall(self):
        source = "def f = 12\n" + \
                 "def f = 34"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testAmbiguousOverloadWithoutCallInClass(self):
        source = "class Foo\n" + \
                 "  def f = 12\n" + \
                 "  def f = 34"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testAmbiguousOverloadGlobal(self):
        source = "def f(a: String, b: Object) = 12\n" + \
                 "def f(a: Object, b: String) = 34\n" + \
                 "var x = f(\"a\", \"b\")"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testAmbiguousOverloadMethods(self):
        source = "class Foo\n" + \
                 "  def f(a: Object, b: String) = 12\n" + \
                 "  def f(a: String, b: Object) = 34\n" + \
                 "def g(foo: Foo) = foo.f(\"a\", \"b\")"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testSimpleOverload(self):
        source = "def f(x: i32) = 2i32 * x\n" + \
                 "def f(x: f32) = 2.000000f32 * x\n" + \
                 "def g =\n" + \
                 "  f(1i32)\n" + \
                 "  f(1.000000f32)"
        info = self.analyzeFromSource(source)
        statements = info.ast.modules[0].definitions[2].body.statements
        self.assertEquals(I32Type, info.getType(statements[0]))
        self.assertEquals(F32Type, info.getType(statements[1]))

    def testOverloadEqualType(self):
        source = "def f(x: Object) = x\n" + \
                 "def f(x: String) = x\n" + \
                 "def g(x: String) = f(x)"
        info = self.analyzeFromSource(source)
        g = info.package.findFunction(name="g")
        self.assertEquals(getStringType(), g.returnType)

    def testOverloadCloserType(self):
        source = "class A\n" + \
                 "class B <: A\n" + \
                 "class C <: B\n" + \
                 "def f(a: A) = true\n" + \
                 "def f(b: B) = 12\n" + \
                 "def g(c: C) = f(c)"
        info = self.analyzeFromSource(source)
        g = info.package.findFunction(name="g")
        self.assertEquals(I64Type, g.returnType)

    def testOverloadWithTypeParameter(self):
        source = "def f[static T] = ()\n" + \
                 "def f = ()\n" + \
                 "def g = f[Object]"
        info = self.analyzeFromSource(source)
        use = info.getUseInfo(info.ast.modules[0].definitions[2].body)
        f = info.package.findFunction(name="f", pred=lambda fn: len(fn.typeParameters) == 1)
        self.assertIs(use.defnInfo.irDefn, f)

    def testOverloadOnTypeParameterBounds(self):
        source = "class A\n" + \
                 "def f[static T] = ()\n" + \
                 "def f[static T <: A] = ()\n" + \
                 "def g = f[Object]"
        info = self.analyzeFromSource(source)
        use = info.getUseInfo(info.ast.modules[0].definitions[3].body)
        A = info.package.findClass(name="A")
        pred = lambda fn: len(fn.typeParameters) == 1 and \
                          fn.typeParameters[0].upperBound.clas is getRootClass()
        f = info.package.findFunction(name="f", pred=pred)
        self.assertIs(use.defnInfo.irDefn, f)

    def testOverloadWithSubstitution(self):
        source = "class C[static T]\n" + \
                 "  static def f(x: T) = true\n" + \
                 "import C[String].f\n" + \
                 "def f(x: Object) = 12\n" + \
                 "def g(x: String) = f(x)"
        info = self.analyzeFromSource(source)
        g = info.package.findFunction(name="g")
        self.assertEquals(BooleanType, g.returnType)

    def testIdentityTypeParameter(self):
        source = "def id[static T](o: T) = o\n" + \
                 "def f(o: String) = id[String](o)"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(getStringType(), f.returnType)

    def testTypeParametersDependInOrder(self):
        source = "def f[static S, static T <: S, static U <: T] = ()"
        info = self.analyzeFromSource(source)
        # pass if no exception
        source = "def f[static U <: T, static T <: S, static S] = ()"
        self.assertRaises(ScopeException, self.analyzeFromSource, source)

    def testTypeParameterLookup(self):
        source = "class C\n" + \
                 "  var x: i64\n" + \
                 "def f[static T <: C](o: T) = o.x"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        self.assertEquals(I64Type, f.returnType)

    def testPrimitiveTypeArguments(self):
        source = "def id[static T](x: T) = x\n" + \
                 "def f = id[i64](12)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testUseTypeParameterInnerFunctionExplicit(self):
        source = "def id-outer[static T] =\n" + \
                 "  def id-inner(x: T) = x"
        info = self.analyzeFromSource(source)
        paramType = info.getType(info.ast.modules[0].definitions[0].body.statements[0].parameters[0])
        T = info.package.findTypeParameter(name="id-outer.T")
        self.assertEquals(VariableType(T), paramType)
        retTy = info.package.findFunction(name="id-outer.id-inner").returnType
        self.assertEquals(VariableType(T), retTy)

    def testUseTypeParameterInnerFunctionImplicit(self):
        source = "def id-outer[static T](x: T) =\n" + \
                 "  def id-inner = x"
        info = self.analyzeFromSource(source)
        xType = info.getType(info.ast.modules[0].definitions[0].body.statements[0].body)
        T = info.package.findTypeParameter(name="id-outer.T")
        self.assertEquals(VariableType(T), xType)

    def testCallInnerFunctionWithImplicitTypeParameter(self):
        source = "def id-outer[static T](x: T) =\n" + \
                 "  def id-inner = x\n" + \
                 "  id-inner"
        info = self.analyzeFromSource(source)
        callType = info.getType(info.ast.modules[0].definitions[0].body.statements[1])
        T = info.package.findTypeParameter(name="id-outer.T")
        self.assertEquals(VariableType(T), callType)

    def testClassWithTypeParameter(self):
        source = "class Box[static T](x: T)\n" + \
                 "  def get = x\n" + \
                 "  def set(y: T) =\n" + \
                 "    x = y\n" + \
                 "    ()"
        info = self.analyzeFromSource(source)
        Box = info.package.findClass(name="Box")
        T = info.package.findTypeParameter(name="Box.T")
        get = info.package.findFunction(name="Box.get")
        set = info.package.findFunction(name="Box.set")
        TTy = VariableType(T)
        BoxTy = ClassType(Box, (TTy,), None)

        self.assertEquals([BoxTy], Box.initializer.parameterTypes)
        self.assertEquals([BoxTy, TTy], Box.constructors[0].parameterTypes)
        self.assertEquals([BoxTy], get.parameterTypes)
        self.assertEquals(TTy, get.returnType)
        self.assertEquals([BoxTy, TTy], set.parameterTypes)
        self.assertEquals(UnitType, set.returnType)

    def testCallCtorWithTypeParameter(self):
        source = "class C\n" + \
                 "class Box[static T](x: T)\n" + \
                 "def f(c: C) = Box[C](c)"
        info = self.analyzeFromSource(source)
        Box = info.package.findClass(name="Box")
        C = info.package.findClass(name="C")
        f = info.package.findFunction(name="f")
        ty = ClassType(Box, (ClassType(C),))
        self.assertEquals(ty, f.returnType)
        self.assertEquals(ty, info.getType(info.ast.modules[0].definitions[2].body))

    def testLoadFieldWithTypeParameter(self):
        source = "class Box[static T](value: T)\n" + \
                 "def f(box: Box[String]) = box.value"
        info = self.analyzeFromSource(source)
        self.assertEquals(getStringType(), info.getType(info.ast.modules[0].definitions[1].body))

    def testLoadInheritedFieldWithTypeParameter(self):
        source = "class Box[static T](value: T)\n" + \
                 "class SubBox <: Box[String]\n" + \
                 "  def this(s: String) = super(s)\n" + \
                 "def f(box: SubBox) = box.value"
        info = self.analyzeFromSource(source)
        self.assertEquals(getStringType(), info.getType(info.ast.modules[0].definitions[2].body))

    def testStoreSubtypeToTypeParameterField(self):
        source = "class A\n" + \
                 "class B <: A\n" + \
                 "class Box[static T](value: T)\n" + \
                 "def f(box: Box[A], b: B) =\n" + \
                 "  box.value = b"
        info = self.analyzeFromSource(source)
        self.assertEquals(UnitType, info.getType(info.ast.modules[0].definitions[3].body))

    def testCallInheritedMethodWithTypeParameter(self):
        source = "class A[static T](val: T)\n" + \
                 "  def get = val\n" + \
                 "class B <: A[Object]\n" + \
                 "  def this(val: Object) =\n" + \
                 "    super(val)\n" + \
                 "def f(b: B) = b.get"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        ty = getRootClassType()
        self.assertEquals(ty, f.returnType)
        self.assertEquals([ty], info.getCallInfo(info.ast.modules[0].definitions[2].body).typeArguments)

    def testOverrideInheritedMethodWithTypeParameter(self):
        source = "abstract class Function[static P, static R]\n" + \
                 "  abstract def apply(x: P): R\n" + \
                 "class AppendString <: Function[String, String]\n" + \
                 "  override def apply(x: String): String = x + \"foo\""
        info = self.analyzeFromSource(source)
        abstractApply = info.package.findFunction(name="Function.apply", flag=ABSTRACT)
        AppendString = info.package.findClass(name="AppendString")
        concreteApply = info.package.findFunction(name="AppendString.apply", clas=AppendString)
        self.assertEquals([abstractApply.id], [o.id for o in concreteApply.overrides])

    def testTypeParameterWithReversedBounds(self):
        source = "class A[static T <: Nothing >: Object]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testTypeParameterWithUnrelatedBound(self):
        source = "class A[static S, static T, static U <: S >: T]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCovariantTypeParameterInConstField(self):
        source = "class Foo[static +T](x: T)"
        self.analyzeFromSource(source)
        # pass if no error

    def testCovariantTypeParameterInVarField(self):
        source = "class Foo[static +T](var x: T)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCovariantTypeParameterInMethodParam(self):
        source = "class Foo[static +T]\n" + \
                 "  def m(x: T) = ()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCovariantTypeParameterInMethodReturn(self):
        source = "abstract class Foo[static +T]\n" + \
                 "  abstract def m: T"
        self.analyzeFromSource(source)
        # pass if no error

    def testCovariantTypeParameterInCtor(self):
        source = "class Foo[static +T]\n" + \
                 "  def this(x: T) = ()"
        self.analyzeFromSource(source)
        # pass if no error

    def testContravariantTypeParameterInField(self):
        source = "class Foo[static -T](x: T)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testContravariantTypeParameterInMethodParam(self):
        source = "class Foo[static -T]\n" + \
                 "  def m(x: T) = ()"
        self.analyzeFromSource(source)
        # pass if no error

    def testContravariantTypeParameterInMethodReturn(self):
        source = "abstract class Foo[static -T]\n" + \
                 "  abstract def m: T"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testContravariantTypeParameterInInferredMethodReturn(self):
        source = "class Foo[static -T]\n" + \
                 "  def m(x: T) = x"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCovariantParamInCovariantClass(self):
        source = "class Source[static +S]\n" + \
                 "class Foo[static +T]\n" + \
                 "  def m(x: Source[T]) = ()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testCovariantParamInContravariantClass(self):
        source = "class Source[static +S]\n" + \
                 "class Foo[static -T]\n" + \
                 "  def m(x: Source[T]) = ()"
        self.analyzeFromSource(source)
        # pass if no error

    def testCovariantReturnInCovariantClass(self):
        source = "class Source[static +S]\n" + \
                 "abstract class Foo[static +T]\n" + \
                 "  abstract def m: Source[T]"
        self.analyzeFromSource(source)
        # pass if no error

    def testCovariantReturnInContravariantClass(self):
        source = "class Source[static +S]\n" + \
                 "abstract class Foo[static -T]\n" + \
                 "  abstract def m: Source[T]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testContravariantParamInCovariantClass(self):
        source = "class Sink[static -S]\n" + \
                 "class Foo[static +T]\n" + \
                 "  def m(x: Sink[T]) = ()"
        self.analyzeFromSource(source)
        # pass if no error

    def testContravariantParamInContravariantClass(self):
        source = "class Sink[static -S]\n" + \
                 "class Foo[static -T]\n" + \
                 "  def m(x: Sink[T]) = ()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testContravariantReturnInCovariantClass(self):
        source = "class Sink[static -S]\n" + \
                 "abstract class Foo[static +T]\n" + \
                 "  abstract def m: Sink[T]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testContravariantReturnInContravariantClass(self):
        source = "class Sink[static -S]\n" + \
                 "abstract class Foo[static -T]\n" + \
                 "  abstract def m: Sink[T]"
        self.analyzeFromSource(source)
        # pass if no error

    def testCovariantInfiniteCombine(self):
        source = "class A[static +T]\n" + \
                 "class B <: A[B]\n" + \
                 "class C <: A[C]\n" + \
                 "def f(b: B, c: C) = if (true) b else c"
        info = self.analyzeFromSource(source)
        f = info.package.findFunction(name="f")
        A = info.package.findClass(name="A")
        expected = ClassType(A, (getRootClassType(),))
        self.assertEquals(expected, f.returnType)

    def testNoDefaultSuperCtor(self):
        source = "class Foo(x: i64)\n" + \
                 "class Bar <: Foo"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testOverloadedDefaultSuperCtor(self):
        source = "class Foo\n" + \
                 "  def this(x: i64) = ()\n" + \
                 "  def this(x: boolean) = ()\n" + \
                 "class Bar <: Foo(true)"
        info = self.analyzeFromSource(source)
        Foo = info.package.findClass(name="Foo")
        superctor = Foo.constructors[1]
        self.assertIs(superctor, info.getUseInfo(info.ast.modules[0].definitions[1]).defnInfo.irDefn)

    def testOverloadedPrimarySuperCtor(self):
        source = "class Foo\n" + \
                 "  def this(x: i64) = ()\n" + \
                 "  def this(x: boolean) = ()\n" + \
                 "class Bar(x: boolean) <: Foo(x)"
        info = self.analyzeFromSource(source)
        Foo = info.package.findClass(name="Foo")
        superctor = Foo.constructors[1]
        self.assertIs(superctor, info.getUseInfo(info.ast.modules[0].definitions[1]).defnInfo.irDefn)

    def testOverloadedAlternateCtor(self):
        source = "class Foo\n" + \
                 "  def this = this(true)\n" + \
                 "  def this(x: i64) = ()\n" + \
                 "  def this(x: boolean) = ()"
        info = self.analyzeFromSource(source)
        Foo = info.package.findClass(name="Foo")
        call = info.ast.modules[0].definitions[0].members[0].body
        calleeCtor = Foo.constructors[2]
        self.assertIs(calleeCtor, info.getUseInfo(call).defnInfo.irDefn)

    def testEnsureParamTypeInfoForDefaultCtor(self):
        source = "let x = Foo()\n" + \
                 "class Foo"
        info = self.analyzeFromSource(source)
        Foo = info.package.findClass(name="Foo")
        ctor = Foo.constructors[0]
        self.assertEquals([ClassType(Foo)], ctor.parameterTypes)

    def testClassWithArrayElements(self):
        source = "final class Foo[static T]\n" + \
                 "  arrayelements T, get, set, length"
        info = self.analyzeFromSource(source)
        T = info.package.findTypeParameter(name="Foo.T")
        TType = VariableType(T)
        Foo = info.package.findClass(name="Foo")
        self.assertEquals(TType, Foo.elementType)
        self.assertIn(ARRAY, Foo.flags)
        FooType = ClassType(Foo, (TType,))

        getMethod = info.package.findFunction(name="Foo.get")
        self.assertEquals(self.makeFunction("Foo.get", typeParameters=[T], returnType=TType,
                                            parameterTypes=[FooType, I32Type],
                                            compileHint=ARRAY_ELEMENT_GET_HINT),
                          getMethod)

        setMethod = info.package.findFunction(name="Foo.set")
        self.assertEquals(self.makeFunction("Foo.set", typeParameters=[T], returnType=UnitType,
                                            parameterTypes=[FooType, I32Type, TType],
                                            compileHint=ARRAY_ELEMENT_SET_HINT),
                          setMethod)

        lengthMethod = info.package.findFunction(name="Foo.length")
        self.assertEquals(self.makeFunction("Foo.length", typeParameters=[T],
                                            returnType=I32Type, parameterTypes=[FooType],
                                            compileHint=ARRAY_ELEMENT_LENGTH_HINT),
                          lengthMethod)

    def testClassWithMutableCovariantArrayElements(self):
        source = "final class Array[static +T]\n" + \
                 "  arrayelements T, get, set, length"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testClassWithImmutableCovariantArrayElements(self):
        source = "final class Array[static +T]\n" + \
                 "  final arrayelements T, get, set, length"
        self.analyzeFromSource(source)
        # pass if no exception is raised

    def testDerivedArrayClassWithFields(self):
        source = "class Array\n" + \
                 "  arrayelements Object, get, set, length\n" + \
                 "class Derived <: Array\n" + \
                 "  let x = 12"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testDerivedArrayClassWithMoreElements(self):
        source = "class Array\n" + \
                 "  arrayelements Object, get, set, length\n" + \
                 "class Derived <: Array\n" + \
                 "  arrayelements i32, get, set, length"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testNewArray(self):
        source = "final class Array[static T]\n" + \
                 "  arrayelements T, get, set, length\n" + \
                 "def f = new(12i32) Array[String]"
        info = self.analyzeFromSource(source)
        Array = info.package.findClass(name="Array")
        ast = info.ast.modules[0].definitions[-1].body
        self.assertEquals(I32Type, info.getType(ast.length))
        self.assertEquals(ClassType(Array, (getStringType(),)), info.getType(ast.ty))

    def testNewArrayBadLength(self):
        source = "final class Array[static T]\n" + \
                 "  arrayelements T, get, set, length\n" + \
                 "def f = new(()) Array[String]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testNewArrayPrimitive(self):
        source = "def f = new(12i32) i32"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testNewArrayNonArray(self):
        source = "class NonArray\n" + \
                 "def f = new(12i32) NonArray"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testArrayWithoutNew(self):
        source = "final class Array[static T]\n" + \
                 "  arrayelements T, get, set, length\n" + \
                 "def f = Array[String]()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    # Tests for usage
    def testUseClassBeforeDefinition(self):
        source = "def f = C()\n" + \
                 "class C\n" + \
                 "  def this = ()"
        info = self.analyzeFromSource(source)
        ty = ClassType(info.package.findClass(name="C"))
        self.assertEquals(ty, info.getType(info.ast.modules[0].definitions[0].body))

    def testRedefinedSymbol(self):
        source = "var x = 12\n" + \
                 "var x = 34"
        self.assertRaises(ScopeException, self.analyzeFromSource, source)

    def testUseGlobalVarInGlobal(self):
        source = "var x = 12\n" + \
                 "var y = x"
        info = self.analyzeFromSource(source)
        self.assertIs(info.getDefnInfo(info.ast.modules[0].definitions[0].pattern),
                      info.getUseInfo(info.ast.modules[0].definitions[1].expression).defnInfo)

    def testUseGlobalVarInFunction(self):
        source = "var x = 12\n" + \
                 "def f = x"
        info = self.analyzeFromSource(source)
        self.assertIs(info.getDefnInfo(info.ast.modules[0].definitions[0].pattern),
                      info.getUseInfo(info.ast.modules[0].definitions[1].body).defnInfo)

    def testUseGlobalVarInClass(self):
        source = "var x = 12\n" + \
                 "class C\n" + \
                 "  var y = x"
        info = self.analyzeFromSource(source)
        ast = info.ast
        self.assertIs(info.getDefnInfo(ast.modules[0].definitions[0].pattern),
                      info.getUseInfo(ast.modules[0].definitions[1].members[0].expression).defnInfo)

    def testUseGlobalFunctionInGlobal(self):
        source = "def f = 12\n" + \
                 "var x = f"
        info = self.analyzeFromSource(source)
        self.assertIs(info.getDefnInfo(info.ast.modules[0].definitions[0]),
                      info.getUseInfo(info.ast.modules[0].definitions[1].expression).defnInfo)

    def testUseGlobalFunctionInFunction(self):
        source = "def f = 12\n" + \
                 "def g = f"
        info = self.analyzeFromSource(source)
        self.assertIs(info.getDefnInfo(info.ast.modules[0].definitions[0]),
                      info.getUseInfo(info.ast.modules[0].definitions[1].body).defnInfo)

    def testUseGlobalFunctionInClass(self):
        source = "def f = 12\n" + \
                 "class C\n" + \
                 "  var x = f"
        info = self.analyzeFromSource(source)
        self.assertIs(info.getDefnInfo(info.ast.modules[0].definitions[0]),
                      info.getUseInfo(info.ast.modules[0].definitions[1].members[0].expression).defnInfo)

    def testUseGlobalClassInGlobal(self):
        source = "class C\n" + \
                 "  def this = ()\n" + \
                 "var x = C()"
        info = self.analyzeFromSource(source)
        self.assertIs(info.getDefnInfo(info.ast.modules[0].definitions[0].members[0]),
                      info.getUseInfo(info.ast.modules[0].definitions[1].expression).defnInfo)

    def testUseGlobalClassInFunction(self):
        source = "class C\n" + \
                 "  def this = ()\n" + \
                 "def f = C()"
        info = self.analyzeFromSource(source)
        self.assertIs(info.getDefnInfo(info.ast.modules[0].definitions[0].members[0]),
                      info.getUseInfo(info.ast.modules[0].definitions[1].body).defnInfo)

    def testUseGlobalClassInClass(self):
        source = "class C\n" + \
                 "  def this = ()\n" + \
                 "class D\n" + \
                 "  var x = C()"
        info = self.analyzeFromSource(source)
        self.assertIs(info.getDefnInfo(info.ast.modules[0].definitions[0].members[0]),
                      info.getUseInfo(info.ast.modules[0].definitions[1].members[0].expression).defnInfo)

    def testImportStaticMethodFromClass(self):
        source = "class Foo\n" + \
                 "  static def f = 12\n" + \
                 "import Foo.f as g\n" + \
                 "let x = g"
        info = self.analyzeFromSource(source)
        x = info.package.findGlobal(name="x")
        self.assertEquals(I64Type, x.type)

    def testImportStaticMethodFromClassWithTypeParams(self):
        source = "class Foo[static T]\n" + \
                 "  static def id(x: T) = x\n" + \
                 "import Foo[String].id\n" + \
                 "let x = id(\"blarg\")"
        info = self.analyzeFromSource(source)
        x = info.package.findGlobal(name="x")
        self.assertEquals(getStringType(), x.type)

    def testImportStaticMethodFromClassWithTypeParamsOutOfBounds(self):
        source = "class Foo[static T <: String]\n" + \
                 "  static def id(x: T) = x\n" + \
                 "import Foo[Object].id\n" + \
                 "let x = id(\"blarg\")"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testImportGlobalFromPackage(self):
        foo = Package(name=Name(["foo"]))
        bar = foo.addGlobal(Name(["bar"]), sourceName="bar",
                            type=I64Type, flags=frozenset([PUBLIC]))
        source = "import foo.bar as baz\n" + \
                 "let x = baz"
        info = self.analyzeFromSource(source, packageLoader=FakePackageLoader([foo]))
        x = info.package.findGlobal(name="x")
        self.assertEquals(I64Type, x.type)

    # Regression tests
    def testPrimaryCtorHasCorrectScope(self):
        source = "class Foo\n" + \
                 "  def make-bar = Bar(1)\n" + \
                 "class Bar(x: i64)"
        info = self.analyzeFromSource(source)
        barCtor = info.getDefnInfo(info.ast.modules[0].definitions[1].constructor).irDefn
        usedCtor = info.getUseInfo(info.ast.modules[0].definitions[0].members[0].body).defnInfo.irDefn
        self.assertIs(barCtor, usedCtor)

    def testSubstituteBoundsWhenCalling(self):
        source = "class Ordered[static T]\n" + \
                 "class Integer <: Ordered[Integer]\n" + \
                 "def sort[static S <: Ordered[S]] = ()\n" + \
                 "def f = sort[Integer]"
        self.analyzeFromSource(source)
        # pass if no error

    def testPublicGlobalPrivateClass(self):
        source = "class Foo\n" + \
                 "public let x = Foo"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPublicGlobalPrivateClassWithArg(self):
        source = "class Foo\n" + \
                 "public class Bar[static T]\n" + \
                 "public var x = Bar[Foo]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPublicFunctionPrivateTypeParam(self):
        source = "class Foo\n" + \
                 "public def f[static T <: Foo] = ()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPublicFunctionPrivateParam(self):
        source = "class Foo\n" + \
                 "public def f(foo: Foo) = ()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPublicFunctionPrivateReturn(self):
        source = "class Foo\n" + \
                 "public def f = Foo"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPublicClassPrivateTypeParam(self):
        source = "class Foo\n" + \
                 "public class Bar[static T <: Foo]"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPublicClassPrivateParam(self):
        source = "class Foo\n" + \
                 "public class Bar(foo: Foo)"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPublicClassPrivateBase(self):
        source = "class Foo\n" + \
                 "public class Bar <: Foo"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPublicClassPrivateMemberType(self):
        source = "class Foo\n" + \
                 "public class Bar\n" + \
                 "  public let x: Foo"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testPublicClassProtectedMemberPrivateType(self):
        source = "class Foo\n" + \
                 "public class Bar\n" + \
                 "  protected let x: Foo"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testInstantiateNothing(self):
        source = "let g = Nothing()"
        self.assertRaises(TypeException, self.analyzeFromSource, source)

    def testSubclassNothing(self):
        source = "class Foo <: Nothing"
        self.assertRaises(InheritanceException, self.analyzeFromSource, source)

    def testBrokenOverride(self):
        source = "class A\n" + \
                 "class B <: A\n" + \
                 "def test(d: D) = d.f\n" + \
                 "class C\n" + \
                 "  def f: B = B()\n" + \
                 "class D\n" + \
                 "  def f = A()"
        self.analyzeFromSource(source)

    def testMatchErasedSubclass(self):
        source = OPTION_SOURCE + \
                 "class A[static +T]\n" + \
                 "class B[static +T] <: A[T]\n" + \
                 "  static def try-match(obj: Object) = None\n" + \
                 "def f[static T](a: A[T]) =\n" + \
                 "  match (a)\n" + \
                 "    case _: B[_] => 1\n" + \
                 "    case _ => 2"
        self.analyzeFromSource(source)

    def testFieldWithBoundedTypeArguments(self):
        source = "trait Hash[static -T]\n" + \
                 "class HashTable[static K <: Hash[K]]\n" + \
                 "class HashSet[static K <: Hash[K]]\n" + \
                 "  let table = HashTable[K]()"
        self.analyzeFromSource(source)

    def testMethodWithBoundedTypeArguments(self):
        source = "trait Hash[static -T]\n" + \
                 "class HashTable[static K <: Hash[K]]\n" + \
                 "abstract class HashSet[static K <: Hash[K]]\n" + \
                 "  abstract def new-table: HashTable[K]"
        self.analyzeFromSource(source)

    def testExternClassWithoutVisibleCtor(self):
        foo = Package(name=Name(["foo"]))
        Bar = foo.addClass(Name(["Bar"]), sourceName="Bar", typeParameters=[],
                           supertypes=[getRootClassType()],
                           constructors=[], fields=[],
                           methods=[], flags=frozenset([PUBLIC]))
        loader = FakePackageLoader([foo])

        source = "let x = foo.Bar()"
        self.assertRaises(TypeException, self.analyzeFromSource, source, packageLoader=loader)

    def testOptionAndTupleExternalizedInDestructure(self):
        import sys
        sys.setrecursionlimit(10000)
        std = Package(name=Name(["std"]))
        Option = std.addClass(Name(["Option"]), sourceName="Option",
                              typeParameters=[],
                              supertypes=[getRootClassType()],
                              constructors=[], fields=[],
                              methods=[], flags=frozenset([PUBLIC, ABSTRACT]))
        OptionT = std.addTypeParameter(Option, Name(["Option", "T"]),
                                       upperBound=getRootClassType(),
                                       lowerBound=getNothingClassType(),
                                       flags=frozenset([STATIC, COVARIANT]))
        OptionType = ClassType.forReceiver(Option)
        OptionIsDefined = std.addFunction(Name(["Option", "is-defined"]),
                                          sourceName="is-defined",
                                          returnType=BooleanType, typeParameters=[OptionT],
                                          parameterTypes=[OptionType],
                                          flags=frozenset([PUBLIC, ABSTRACT, METHOD]),
                                          definingClass=Option)
        OptionGet = std.addFunction(Name(["Option", "get"]), sourceName="get",
                                    returnType=VariableType(OptionT),
                                    parameterTypes=[OptionType],
                                    flags=frozenset([PUBLIC, ABSTRACT, METHOD]),
                                    definingClass=Option)
        Option.methods.extend([OptionIsDefined, OptionGet])
        Non = std.addGlobal(Name(["None"]), sourceName="None",
                            type=ClassType(Option, (getNothingClassType(),)),
                            flags=frozenset([PUBLIC, LET]))
        Some = std.addClass(Name(["Some"]), sourceName="Some",
                            typeParameters=[],
                            supertypes=[None, getRootClassType()],
                            constructors=[], fields=[], methods=[],
                            flags=frozenset([PUBLIC, FINAL]))
        SomeT = std.addTypeParameter(Some, Name(["Some", "T"]),
                                     upperBound=getRootClassType(),
                                     lowerBound=getNothingClassType(),
                                     flags=frozenset([STATIC, COVARIANT]))
        SomeTType = VariableType(SomeT)
        Some.supertypes[0] = ClassType(Option, (SomeTType,))
        SomeType = ClassType.forReceiver(Some)
        SomeCtor = std.addFunction(Name(["Some", CONSTRUCTOR_SUFFIX]),
                                   returnType=UnitType,
                                   typeParameters=[SomeT],
                                   parameterTypes=[SomeType, SomeTType],
                                   flags=frozenset([PUBLIC, METHOD, CONSTRUCTOR]),
                                   definingClass=Some)
        Some.constructors.append(SomeCtor)
        Tuple2 = std.addClass(Name(["Tuple2"]), sourceName="Tuple2",
                              typeParameters=[],
                              supertypes=[getRootClassType()],
                              constructors=[], fields=[],
                              methods=[], flags=frozenset([PUBLIC, FINAL]))
        Tuple2T1 = std.addTypeParameter(Tuple2, Name(["Tuple2", "T1"]),
                                        upperBound=getRootClassType(),
                                        lowerBound=getNothingClassType(),
                                        flags=frozenset([STATIC, COVARIANT]))
        Tuple2T1Type = VariableType(Tuple2T1)
        Tuple2T2 = std.addTypeParameter(Tuple2, Name(["Tuple2", "T2"]),
                                        upperBound=getRootClassType(),
                                        lowerBound=getNothingClassType(),
                                        flags=frozenset([STATIC, COVARIANT]))
        Tuple2T2Type = VariableType(Tuple2T2)
        Tuple2Type = ClassType.forReceiver(Tuple2)
        Tuple2Ctor = std.addFunction(Name(["Tuple2", CONSTRUCTOR_SUFFIX]),
                                     returnType=UnitType,
                                     typeParameters=[Tuple2T1, Tuple2T2],
                                     parameterTypes=[Tuple2Type, Tuple2T1Type, Tuple2T2Type],
                                     flags=frozenset([PUBLIC, METHOD, CONSTRUCTOR]),
                                     definingClass=Tuple2)
        Tuple2.constructors.append(Tuple2Ctor)

        packageLoader = FakePackageLoader([std])
        source = "import std.None, Option, Some\n" + \
                 "abstract class Expr\n" + \
                 "final class AddExpr(left: Expr, right: Expr) <: Expr\n" + \
                 "  static def try-match(obj: Object): Option[(Expr, Expr)] =\n" + \
                 "    match (obj)\n" + \
                 "      case e: AddExpr => Some[(Expr, Expr)]((e.left, e.right))\n" + \
                 "      case _ => None\n" + \
                 "def f(obj: Object) =\n" + \
                 "  match (obj)\n" + \
                 "    case AddExpr(a, b) => true\n" + \
                 "    case _ => false"
        info = self.analyzeFromSource(source, packageLoader=packageLoader, isUsingStd=True)

        stdExternInfoNames = [defn.name for defn in info.iterStdExternInfo()]
        self.assertIn(Option.name, stdExternInfoNames)
        self.assertIn(OptionIsDefined.name, stdExternInfoNames)
        self.assertIn(OptionGet.name, stdExternInfoNames)
        self.assertIn(Tuple2.name, stdExternInfoNames)


if __name__ == "__main__":
    unittest.main()
