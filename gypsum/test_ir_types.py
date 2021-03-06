# Copyright Jay Conrod. All rights reserved.
#
# This file is part of Gypsum. Use of this source code is governed by
# the GPL license that can be found in the LICENSE.txt file.


import unittest

from builtins import *
from errors import * #For TypeException
from flags import * # For CONTRAVARIANT and COVARIANT
from ids import TARGET_PACKAGE_ID
from ir import *
from ir import * # Needed for Class()
from ir_types import *
from location import *
from name import Name
from utils import *


class TestIrTypes(unittest.TestCase):
    registerBuiltins(lambda name, ir: None)

    def setUp(self):
        super(TestIrTypes, self).setUp()
        self.package = Package(id=TARGET_PACKAGE_ID)
        self.A = self.package.addClass(Name(["A"]), typeParameters=[],
                                       supertypes=[getRootClassType()])
        self.B = self.package.addClass(Name(["B"]), typeParameters=[],
                                       supertypes=[ClassType(self.A)] + self.A.supertypes)
        self.C = self.package.addClass(Name(["C"]), typeParameters=[],
                                       supertypes=[ClassType(self.B)] + self.B.supertypes)
        self.P = self.package.addClass(Name(["P"]), typeParameters=[],
                                       supertypes=[getRootClassType()])
        self.X = self.package.addTypeParameter(self.P, Name(["X"]),
                                               upperBound=getRootClassType(),
                                               lowerBound=getNothingClassType())
        self.Y = self.package.addTypeParameter(self.P, Name(["Y"]),
                                               upperBound=getRootClassType(),
                                               lowerBound=getNothingClassType())

    def testSubtypeSelf(self):
        self.assertTrue(ClassType(self.A).isSubtypeOf(ClassType(self.A)))

    def testSubtypeParent(self):
        self.assertTrue(ClassType(self.B).isSubtypeOf(ClassType(self.A)))
        self.assertFalse(ClassType(self.A).isSubtypeOf(ClassType(self.B)))

    def testSubtypeNull(self):
        ATy = ClassType(self.A, (), frozenset([NULLABLE_TYPE_FLAG]))
        self.assertTrue(getNullType().isSubtypeOf(ATy))

    def testSubtypeParameterSelf(self):
        T = self.package.addTypeParameter(None, Name(["T"]),
                                          upperBound=ClassType(self.A),
                                          lowerBound=ClassType(self.B))
        ty = VariableType(T)
        self.assertTrue(ty.isSubtypeOf(ty))

    def testSubtypeParametersOverlapping(self):
        T = self.package.addTypeParameter(None, Name(["T"]), upperBound=ClassType(self.A),
                                          lowerBound=ClassType(self.C))
        S = self.package.addTypeParameter(None, Name(["S"]), upperBound=ClassType(self.B),
                                          lowerBound=ClassType(self.C))
        self.assertFalse(VariableType(S).isSubtypeOf(VariableType(T)))

    def testSubtypeParametersNonOverlapping(self):
        T = self.package.addTypeParameter(None, Name(["T"]), upperBound=ClassType(self.A),
                                          lowerBound=ClassType(self.B))
        S = self.package.addTypeParameter(None, Name(["S"]), upperBound=ClassType(self.B),
                                          lowerBound=ClassType(self.C))
        self.assertTrue(VariableType(S).isSubtypeOf(VariableType(T)))

    def testSubtypeParametersTransitiveUpper(self):
        U = self.package.addTypeParameter(None, Name(["U"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        T = self.package.addTypeParameter(None, Name(["T"]), upperBound=VariableType(U),
                                          lowerBound=getNothingClassType())
        S = self.package.addTypeParameter(None, Name(["S"]), upperBound=VariableType(T),
                                          lowerBound=getNothingClassType())
        self.assertTrue(VariableType(S).isSubtypeOf(VariableType(U)))

    def testSubtypeParametersTransitiveLower(self):
        # U, T >: U, S >: T
        # So S <: U
        U = self.package.addTypeParameter(None, Name(["U"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        T = self.package.addTypeParameter(None, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=VariableType(U))
        S = self.package.addTypeParameter(None, Name(["S"]), upperBound=getRootClassType(),
                                          lowerBound=VariableType(T))
        self.assertTrue(VariableType(U).isSubtypeOf(VariableType(S)))

    def testSubtypeParametersTransitiveMiddle(self):
        # M, S <: M, M <: T, so S <: T
        M = self.package.addTypeParameter(None, Name(["M"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        S = self.package.addTypeParameter(None, Name(["S"]), upperBound=VariableType(M),
                                          lowerBound=getNothingClassType())
        T = self.package.addTypeParameter(None, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=VariableType(M))
        self.assertTrue(VariableType(S).isSubtypeOf(VariableType(T)))

    def testSubtypeClassWithParametersSelf(self):
        A = self.package.addClass(Name(["A"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        T = self.package.addTypeParameter(A, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        S = self.package.addTypeParameter(None, Name(["S"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        X = self.package.addClass(Name(["X"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        Y = self.package.addClass(Name(["Y"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        ATty = ClassType(A, (VariableType(T),))
        ASty = ClassType(A, (VariableType(S),))
        AXty = ClassType(A, (ClassType(X),))
        AYty = ClassType(A, (ClassType(Y),))
        self.assertTrue(ATty.isSubtypeOf(ATty))
        self.assertFalse(ATty.isSubtypeOf(ASty))
        self.assertTrue(AXty.isSubtypeOf(AXty))
        self.assertFalse(AXty.isSubtypeOf(AYty))

    def testSubtypeClassWithParametersSubclass(self):
        A = self.package.addClass(Name(["A"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        T = self.package.addTypeParameter(A, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        X = self.package.addClass(Name(["X"]), supertypes=[getRootClassType()])
        Y = self.package.addClass(Name(["Y"]), supertypes=[getRootClassType()])
        AXty = ClassType(A, (ClassType(X),))
        B = self.package.addClass(Name(["B"]), supertypes=[AXty])
        Bty = ClassType(B)
        AYty = ClassType(A, (ClassType(Y),))
        self.assertTrue(Bty.isSubtypeOf(AXty))
        self.assertFalse(Bty.isSubtypeOf(AYty))

    def testSubtypeClassWithParametersSuperclass(self):
        A = self.package.addClass(Name(["A"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        Aty = ClassType(A)
        B = self.package.addClass(Name(["B"]), typeParameters=[], supertypes=[Aty])
        T = self.package.addTypeParameter(B, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        X = self.package.addClass(Name(["X"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        BXty = ClassType(B, (ClassType(X),))
        self.assertTrue(BXty.isSubtypeOf(Aty))

    def testSubtypeWithCovariantParameter(self):
        # Source[A] <: Source[B] with class Source[+T] and A <: B
        B = self.package.addClass(Name(["B"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        Bty = ClassType(B)
        A = self.package.addClass(Name(["A"]), typeParameters=[],
                                  supertypes=[Bty] + B.supertypes)
        Aty = ClassType(A)
        Source = self.package.addClass(Name(["Source"]), typeParameters=[],
                                       supertypes=[getRootClassType()])
        T = self.package.addTypeParameter(Source, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType(),
                                          flags=frozenset([COVARIANT]))
        SourceAty = ClassType(Source, (Aty,))
        SourceBty = ClassType(Source, (Bty,))
        self.assertTrue(SourceAty.isSubtypeOf(SourceBty))
        self.assertFalse(SourceBty.isSubtypeOf(SourceAty))

    def testSubtypeWithContravariantParameter(self):
        # Sink[A] <: Sink[B] with class Sink[-T] and B <: A
        A = self.package.addClass(Name(["A"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        Aty = ClassType(A)
        B = self.package.addClass(Name(["B"]), typeParameters=[], supertypes=[Aty])
        Bty = ClassType(B)
        Sink = self.package.addClass(Name(["Sink"]), typeParameters=[],
                                     supertypes=[getRootClassType()])
        T = self.package.addTypeParameter(Sink, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType(),
                                          flags=frozenset([CONTRAVARIANT]))
        SinkAty = ClassType(Sink, (Aty,))
        SinkBty = ClassType(Sink, (Bty,))
        self.assertTrue(SinkAty.isSubtypeOf(SinkBty))
        self.assertFalse(SinkBty.isSubtypeOf(SinkAty))

    def testSubtypeNothingAndVariable(self):
        T = self.package.addTypeParameter(None, Name(["T"]),
                                          upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        Tty = VariableType(T)
        self.assertTrue(getNothingClassType().isSubtypeOf(Tty))

    def testSubtypeRightExistential(self):
        # class C[T]
        # C[Object] <: forsome [X] C[X]
        C = self.package.addClass(Name(["C"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        T = self.package.addTypeParameter(C, Name(["T"]),
                                          upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        Cty = ClassType(C, (getRootClassType(),))
        X = self.package.addTypeParameter(None, Name(["X"]),
                                          upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        eXty = ExistentialType([X], ClassType(C, (VariableType(X),)))
        self.assertTrue(Cty.isSubtypeOf(eXty))

    def testSubtypeRightExistentialContradiction(self):
        # class A[T]
        # class B[U, V]
        # B[A[String], A[Object]] </: forsome [X <: forsome [Y] A[Y]] B[X, X]
        # At the time this was written, existentials could not be used as bounds. That
        # restriction might be relaxed in the future, and the implementation does not
        # completely rely on it. So it's nice to test that implementation.
        A = self.package.addClass(Name(["A"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        T = self.package.addTypeParameter(A, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        B = self.package.addClass(Name(["B"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        U = self.package.addTypeParameter(B, Name(["U"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        V = self.package.addTypeParameter(B, Name(["V"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        Y = self.package.addTypeParameter(None, Name(["Y"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        X = self.package.addTypeParameter(None, Name(["X"]),
                                          upperBound=ExistentialType([Y], ClassType(A, (VariableType(Y),))),
                                          lowerBound=getNothingClassType())
        leftType = ClassType(B, (ClassType(A, (getStringType(),)), ClassType(A, (getRootClassType(),))))
        rightType = ExistentialType([X], ClassType(B, (VariableType(X), VariableType(X))))
        self.assertFalse(leftType.isSubtypeOf(rightType))

    def testSubtypeRightExistentialFailUpperBound(self):
        X = self.package.addTypeParameter(None, Name(["X"]), upperBound=getStringType(),
                                          lowerBound=getNothingClassType())
        eXType = ExistentialType([X], VariableType(X))
        self.assertTrue(getStringType().isSubtypeOf(eXType))
        self.assertFalse(getRootClassType().isSubtypeOf(eXType))

    def testSubtypeRightExistentialFailLowerBound(self):
        X = self.package.addTypeParameter(None, Name(["X"]), upperBound=getRootClassType(),
                                          lowerBound=getRootClassType())
        eXType = ExistentialType([X], VariableType(X))
        self.assertFalse(getStringType().isSubtypeOf(eXType))
        self.assertTrue(getRootClassType().isSubtypeOf(eXType))

    def testSubtypeRightExistentialSubstituteMultiple(self):
        # class C[S, T]
        # C[String, Object] <: forsome [X] C[X, X]
        C = self.package.addClass(Name(["C"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        S = self.package.addTypeParameter(C, Name(["S"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        T = self.package.addTypeParameter(C, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        X = self.package.addTypeParameter(None, Name(["X"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        XType = VariableType(X)
        CType = ClassType(C, (getStringType(), getRootClassType()))
        eCXType = ExistentialType((X,), ClassType(C, (XType, XType)))
        self.assertTrue(CType.isSubtypeOf(eCXType))

    def testEquivalentExistentials(self):
        X = self.package.addTypeParameter(None, Name(["X"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        Y = self.package.addTypeParameter(None, Name(["Y"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        eX = ExistentialType((X,), VariableType(X))
        eY = ExistentialType((Y,), VariableType(Y))
        self.assertTrue(eX.isSubtypeOf(eY))
        self.assertTrue(eY.isSubtypeOf(eX))
        self.assertTrue(eX.isEquivalent(eY))
        self.assertTrue(eY.isEquivalent(eX))

    def testJointExistentials(self):
        Foo = self.package.addClass(Name(["Foo"]), typeParameters=[],
                                    supertypes=[getRootClassType()])
        S = self.package.addTypeParameter(Foo, Name(["S"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType(),
                                          flags=frozenset([STATIC, COVARIANT]))
        T = self.package.addTypeParameter(Foo, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType(),
                                          flags=frozenset([STATIC, COVARIANT]))
        X = self.package.addTypeParameter(None, Name(["X"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        Y = self.package.addTypeParameter(None, Name(["Y"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        eX = ExistentialType((X,), ClassType(Foo, (VariableType(X), getNothingClassType())))
        eY = ExistentialType((Y,), ClassType(Foo, (getNothingClassType(), VariableType(Y))))
        expected = ExistentialType((X, Y), ClassType(Foo, (VariableType(X), VariableType(Y))))
        self.assertTrue(expected.isEquivalent(eX.lub(eY)))

    def testExistentialOpen(self):
        Foo = self.package.addClass(Name(["Foo"]), typeParameters=[],
                                    supertypes=[getRootClassType()])
        T = self.package.addTypeParameter(Foo, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType(),
                                          flags=frozenset([COVARIANT]))
        FooStringType = ClassType(Foo, (getStringType(),))
        X = self.package.addTypeParameter(None, Name(["X"]), upperBound=getStringType(),
                                          lowerBound=getNothingClassType())
        FooExType = ExistentialType((X,), ClassType(Foo, (VariableType(X),)))
        self.assertTrue(FooExType.isSubtypeOf(FooStringType))

    def testExistentialDifferentBoundsNotEquivalent(self):
        X = self.package.addTypeParameter(None, Name(["X"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        Y = self.package.addTypeParameter(None, Name(["Y"]), upperBound=getStringType(),
                                          lowerBound=getNothingClassType())
        eXType = ExistentialType((X,), VariableType(X))
        eYType = ExistentialType((Y,), VariableType(Y))
        self.assertFalse(eXType.isEquivalent(eYType))

    def testExistentialDifferentBoundsLub(self):
        # class A
        # class B[S]
        # class C[T]
        # A == forsome[X] B[X] lub forsome [Y] C[Y]
        A = self.package.addClass(Name(["A"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        AType = ClassType(A)
        B = self.package.addClass(Name(["B"]), typeParameters=[], supertypes=[AType])
        S = self.package.addTypeParameter(B, Name(["S"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        SType = VariableType(S)
        C = self.package.addClass(Name(["C"]), typeParameters=[], supertypes=[AType])
        T = self.package.addTypeParameter(C, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())

        X = self.package.addTypeParameter(None, Name(["X"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        Y = self.package.addTypeParameter(None, Name(["Y"]), upperBound=getStringType(),
                                          lowerBound=getNothingClassType())
        eBXType = ExistentialType((X,), ClassType(B, (VariableType(X),)))
        eCYType = ExistentialType((Y,), ClassType(C, (VariableType(Y),)))
        self.assertEquals(AType, eBXType.lub(eCYType))

    def testExistentialCombineParametersLub(self):
        # class C[S, T]
        # forsome [X, Y] C[X, Y] == forsome [X] C[X, String] lub forsome [Y] C[Object, Y]
        C = self.package.addClass(Name(["C"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        S = self.package.addTypeParameter(C, Name(["S"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        T = self.package.addTypeParameter(C, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        X = self.package.addTypeParameter(None, Name(["X"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        XType = VariableType(X)
        eXType = ExistentialType((X,), ClassType(C, (XType, getStringType())))
        Y = self.package.addTypeParameter(None, Name(["Y"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        YType = VariableType(Y)
        eYType = ExistentialType((Y,), ClassType(C, (getRootClassType(), YType)))
        eXYType = ExistentialType((X, Y), ClassType(C, (XType, YType)))
        self.assertEquals(eXYType, eXType.lub(eYType))

    def testLubSubTrait(self):
        A = self.package.addTrait(Name(["A"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        ATy = ClassType(A)
        B = self.package.addTrait(Name(["B"]), typeParameters=[],
                                  supertypes=[ATy, getRootClassType()])
        BTy = ClassType(B)
        self.assertEquals(ATy, ATy.lub(BTy))
        self.assertEquals(ATy, BTy.lub(ATy))

    def testLubClassesSharedTraits(self):
        # TODO: when union types are supported the correct result here is C1 | C2.
        Tr1 = self.package.addTrait(Name(["Tr1"]), typeParameters=[],
                                    supertypes=[getRootClassType()])
        Tr1Type = ClassType(Tr1)
        Tr2 = self.package.addTrait(Name(["Tr2"]), typeParameters=[],
                                    supertypes=[getRootClassType()])
        Tr2Type = ClassType(Tr2)
        C1 = self.package.addClass(Name(["C1"]), typeParameters=[],
                                   supertypes=[getRootClassType(), Tr1Type, Tr2Type])
        C1Type = ClassType(C1)
        C2 = self.package.addClass(Name(["C2"]), typeParameters=[],
                                   supertypes=[getRootClassType(), Tr1Type, Tr2Type])
        C2Type = ClassType(C2)
        self.assertEquals(getRootClassType(), C1Type.lub(C2Type))

    def testSubstitute(self):
        T = self.package.addTypeParameter(None, Name(["T"]), upperBound=ClassType(self.A),
                                          lowerBound=ClassType(self.B))
        a = ClassType(self.A)
        b = ClassType(self.B)
        p = ClassType(self.P, tuple(VariableType(pt) for pt in self.P.typeParameters))
        self.assertEquals(UnitType, UnitType.substitute([T], [a]))
        self.assertEquals(a, a.substitute([T], [a]))
        self.assertEquals(a, VariableType(T).substitute([T], [a]))
        self.assertEquals(ClassType(self.P, (a, b)),
                          p.substitute(self.P.typeParameters, [a, b]))

    def testSubstituteForBase(self):
        A = self.package.addClass(Name(["A"]), typeParameters=[],
                                  supertypes=[getRootClassType()])
        T = self.package.addTypeParameter(A, Name(["T"]))
        B = self.package.addClass(Name(["B"]), typeParameters=[],
                                  supertypes=[None, getRootClassType()])
        U = self.package.addTypeParameter(B, Name(["U"]))
        B.supertypes[0] = ClassType(A, (VariableType(U),))
        C = self.package.addClass(Name(["C"]), supertypes=[getRootClassType()])
        D = self.package.addClass(Name(["D"]),
                                  supertypes=[
                                      ClassType(B, (ClassType(C),)),
                                      ClassType(A, (ClassType(C),)),
                                      getRootClassType()
                                  ])
        V = self.package.addTypeParameter(None, Name(["V"]), upperBound=ClassType(D))
        self.assertEquals(ClassType(A, (ClassType(C),)),
                          VariableType(V).substituteForBase(A))

    def testCombineNothing(self):
        aTy = ClassType(self.A)
        nothingTy = getNothingClassType()
        self.assertEquals(aTy, aTy.combine(nothingTy, NoLoc))
        self.assertEquals(aTy, nothingTy.combine(aTy, NoLoc))

    def testCombineNull(self):
        aTy = ClassType(self.A)
        nullTy = getNullType()
        aNullTy = ClassType(self.A, (), frozenset([NULLABLE_TYPE_FLAG]))
        self.assertEquals(aNullTy, aTy.combine(nullTy, NoLoc))
        self.assertEquals(aNullTy, nullTy.combine(aTy, NoLoc))

    def testCombineWithTypeArgs(self):
        pxy = ClassType(self.P, (VariableType(self.X), VariableType(self.Y)))
        pyx = ClassType(self.P, (VariableType(self.Y), VariableType(self.X)))
        self.assertEquals(pxy, pxy.combine(pxy, NoLoc))
        self.assertEquals(self.P.supertypes[0], pxy.combine(pyx, NoLoc))

    def testEffectiveClassTypeForClassType(self):
        aTy = ClassType(self.A)
        self.assertEquals((aTy, []), aTy.effectiveClassType())

    def testEffectiveClassTypeForVariableType(self):
        aTy = ClassType(self.A)
        S = self.package.addTypeParameter(None, Name(["S"]),
                                          upperBound=aTy, lowerBound=getNothingClassType())
        sTy = VariableType(S)
        T = self.package.addTypeParameter(None, Name(["T"]),
                                          upperBound=sTy, lowerBound=getNothingClassType())
        tTy = VariableType(T)
        self.assertEquals((aTy, []), tTy.effectiveClassType())

    def testEffectiveClassTypeForExistentialType(self):
        S = self.package.addTypeParameter(None, Name(["S"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        sTy = VariableType(S)
        T = self.package.addTypeParameter(None, Name(["T"]), upperBound=getRootClassType(),
                                          lowerBound=getNothingClassType())
        tTy = VariableType(T)
        pTy = ClassType(self.P, (sTy, tTy))
        eTy = ExistentialType([S], ExistentialType([T], pTy))
        self.assertEquals((pTy, [S, T]), eTy.effectiveClassType())


if __name__ == "__main__":
    unittest.main()
