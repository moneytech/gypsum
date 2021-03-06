# Copyright Jay Conrod. All rights reserved.
#
# This file is part of Gypsum. Use of this source code is governed by
# the GPL license that can be found in the LICENSE.txt file.

import ast
import errors
import utils

class FormatException(errors.CompileException):
    kind = "format"


class Format(object):
    def __init__(self,
                 indentWidth = 2,
                 linesBetweenImports = 0,
                 linesBetweenTopDefns = 1,
                 linesBetweenInnerDefns = 1,
                 linesBetweenVars = 0,
                 linesBetweenShortFuncs = 0,
                 linesBetweenMisc = 1,
                 spacesBeforeTailComment = 2,
                 newlineAtEnd = True):
        self.indentWidth = indentWidth
        self.linesBetweenImports = linesBetweenImports
        self.linesBetweenTopDefns = linesBetweenTopDefns
        self.linesBetweenInnerDefns = linesBetweenInnerDefns
        self.linesBetweenVars = linesBetweenVars
        self.linesBetweenShortFuncs = linesBetweenShortFuncs
        self.linesBetweenMisc = linesBetweenMisc
        self.spacesBeforeTailComment = spacesBeforeTailComment
        self.newlineAtEnd = newlineAtEnd


class Formatter(ast.NodeVisitor):
    def __init__(self, fmt, info, out):
        assert len(info.ast.modules) == 1
        self._fmt = fmt
        self._info = info
        self._out = out
        self._currentIndent = 0
        self._blank = 0
        self._line = []
        self._begin = True
        self._hanging = False
        self._preserveBlanks = False

    def format(self):
        self.visit(self._info.ast.modules[0])
        self._flush()

    def visitModule(self, node):
        self._writeStatements(node.definitions)
        if self._fmt.newlineAtEnd:
            self._endl()

    def visitAttribute(self, node):
        self._write(node.name)

    def visitVariableDefinition(self, node):
        self._writeAttributes(node.attribs)
        self._write(node.keyword)
        self._write(" ")
        self.visit(node.pattern)
        if node.expression:
            self._write(" = ")
            self.visit(node.expression)

    def visitFunctionDefinition(self, node):
        self._writeAttributes(node.attribs)
        self._write("def ")
        self._write(node.name)
        c = node.name[0]
        isOperator = not ('A' <= c <= 'Z' or 'a' <= c <= 'z' or c == '_')
        if isOperator and (
            node.typeParameters is not None or
            node.parameters is not None or
            node.returnType is not None):
            self._write(" ")
        self._writeTypeParameters(node.typeParameters)
        self._writeParameters(node.parameters)
        if node.returnType:
            self._write(": ")
            self.visit(node.returnType)
        if node.body:
            self._write(" = ")
            self.visit(node.body)

    def visitClassDefinition(self, node):
        self._writeAttributes(node.attribs)
        self._write("class ")
        self._write(node.name)
        self._writeTypeParameters(node.typeParameters)
        if node.constructor:
            self.visit(node.constructor)
        if node.superclass or node.supertraits:
            self._write(" <: ")
            if node.superclass:
                self.visit(node.superclass)
                if node.superArgs:
                    self._writeArguments(node.superArgs)
                if node.supertraits:
                    self._write(", ")
            if node.supertraits:
                self._writeList(node.supertraits, "", ", ", "")
        self._writeBlock(node.members)

    def visitPrimaryConstructorDefinition(self, node):
        if len(node.attribs) > 0:
            self._write(" ")
        self._writeAttributes(node.attribs)
        self._writeParameters(node.parameters, writeEmpty=True)

    def visitArrayElementsStatement(self, node):
        self._writeAttributes(node.attribs)
        self._write("arrayelements ")
        self.visit(node.elementType)
        self._write(", ")
        self.visit(node.getDefn)
        self._write(", ")
        self.visit(node.setDefn)
        self._write(", ")
        self.visit(node.lengthDefn)

    def visitArrayAccessorDefinition(self, node):
        self._writeAttributes(node.attribs)
        self._write(node.name)

    def visitTraitDefinition(self, node):
        self._writeAttributes(node.attribs)
        self._write("trait ")
        self._write(node.name)
        self._writeTypeParameters(node.typeParameters)
        self._writeList(node.supertypes, " <: ", ", ", "")
        self._writeBlock(node.members)

    def visitImportStatement(self, node):
        self._write("import ")
        self._writePrefix(node.prefix)
        if node.bindings is None:
            self._write("_")
        else:
            self._writeList(node.bindings, "", ", ", "")

    def visitImportBinding(self, node):
        self._write(node.name)
        if node.asName:
            self._write(" as ")
            self._write(node.asName)

    def visitScopePrefixComponent(self, node):
        self._write(node.name)
        self._writeTypeArguments(node.typeArguments)

    def visitTypeParameter(self, node):
        self._writeAttributes(node.attribs)
        if node.variance:
            self._write(node.variance)
        self._write(node.name)
        if node.upperBound:
            self._write(" <: ")
            self.visit(node.upperBound)
        if node.lowerBound:
            self._write(" >: ")
            self.visit(node.lowerBound)

    def visitParameter(self, node):
        self._writeAttributes(node.attribs)
        if node.var:
            self._write(node.var)
            self._write(" ")
        self.visit(node.pattern)

    def visitVariablePattern(self, node):
        self._write(node.name)
        if node.ty:
            self._write(": ")
            self.visit(node.ty)

    def visitBlankPattern(self, node):
        self._write("_")
        if node.ty:
            self._write(": ")
            self.visit(node.ty)

    def visitLiteralPattern(self, node):
        self.visit(node.literal)

    def visitTuplePattern(self, node):
        self._writeList(node.patterns, "", ", ", "")

    def visitValuePattern(self, node):
        self._writePrefix(node.prefix)
        self._write(node.name)

    def visitDestructurePattern(self, node):
        self._writeList(node.prefix, "", ".", "")
        self._writeList(node.patterns, "(", ", ", ")")

    def visitUnaryPattern(self, node):
        self._write(node.operator)
        self.visit(node.pattern)

    def visitBinaryPattern(self, node):
        self.visit(node.left)
        self._write(" ")
        self._write(node.operator)
        self._write(" ")
        self.visit(node.right)

    def visitGroupPattern(self, node):
        self._write("(")
        self.visit(node.pattern)
        self._write(")")

    def visitUnitType(self, node):
        self._write("unit")

    def visitI8Type(self, node):
        self._write("i8")

    def visitI16Type(self, node):
        self._write("i16")

    def visitI32Type(self, node):
        self._write("i32")

    def visitI64Type(self, node):
        self._write("i64")

    def visitF32Type(self, node):
        self._write("f32")

    def visitF64Type(self, node):
        self._write("f64")

    def visitBooleanType(self, node):
        self._write("boolean")

    def visitClassType(self, node):
        self._writePrefix(node.prefix)
        self._write(node.name)
        self._writeTypeArguments(node.typeArguments)
        self._writeTypeFlags(node.flags)

    def visitTupleType(self, node):
        self._writeList(node.types, "(", ", ", ")")
        self._writeTypeFlags(node.flags)

    def visitBlankType(self, node):
        self._write("_")

    def visitExistentialType(self, node):
        self._write("forsome ")
        self._writeTypeParameters(node.typeParameters)
        self._write(" ")
        self.visit(node.type)

    def visitFunctionType(self, node):
        if len(node.parameterTypes) == 0:
            self._write("()")
        elif len(node.parameterTypes) == 1:
            self.visit(node.parameterTypes[0])
        else:
            self._writeList(node.parameterTypes, "(", ", ", ")")
        self._write(" -> ")
        self.visit(node.returnType)

    def visitLiteralExpression(self, node):
        self.visit(node.literal)

    def visitVariableExpression(self, node):
        self._write(node.name)

    def visitThisExpression(self, node):
        self._write("this")

    def visitSuperExpression(self, node):
        self._write("super")

    def visitBlockExpression(self, node):
        if (len(node.statements) == 1 and
            isinstance(node.statements[0], ast.BlockExpression) and
            len(node.statements[0].statements) != 0):
            raise FormatException(node.location,
                                  "block expression only contains block expression")

        if len(node.statements) == 0:
            self._write("{}")
        else:
            with _PreserveBlanksScope(self):
                self._writeBlock(node.statements)

    def visitAssignExpression(self, node):
        self.visit(node.left)
        self._write(" = ")
        self.visit(node.right)

    def visitPropertyExpression(self, node):
        self.visit(node.receiver)
        self._write(".")
        self._write(node.propertyName)

    def visitCallExpression(self, node):
        self.visit(node.callee)
        self._writeTypeArguments(node.typeArguments)
        self._writeArguments(node.arguments)

    def visitNewArrayExpression(self, node):
        self._write("new(")
        self.visit(node.length)
        self._write(") ")
        self.visit(node.ty)
        self._writeArguments(node.arguments)

    def visitUnaryExpression(self, node):
        self._write(node.operator)
        self.visit(node.expr)

    def visitBinaryExpression(self, node):
        self.visit(node.left)
        self._write(" ")
        self._write(node.operator)
        self._write(" ")
        self.visit(node.right)

    def visitFunctionValueExpression(self, node):
        self.visit(node.expr)
        self._write(" _")

    def visitTupleExpression(self, node):
        # TODO: this will break function arguments and anything with higher precedence
        self._writeList(node.expressions, "", ", ", "")

    def visitIfExpression(self, node):
        self._write("if (")
        self.visit(node.condition)
        self._write(") ")
        self.visit(node.trueExpr)
        if node.falseExpr:
            self._writeHanging("else ")
            self.visit(node.falseExpr)

    def visitWhileExpression(self, node):
        self._write("while (")
        self.visit(node.condition)
        self._write(") ")
        self.visit(node.body)

    def visitBreakExpression(self, node):
        self._write("break")

    def visitContinueExpression(self, node):
        self._write("continue")

    def visitPartialFunctionExpression(self, node):
        self._writeBlock(node.cases)

    def visitPartialFunctionCase(self, node):
        self._write("case ")
        self.visit(node.pattern)
        if node.condition:
            self._write(" if ")
            self.visit(node.condition)
        self._write(" => ")
        self.visit(node.expression)

    def visitMatchExpression(self, node):
        self._write("match (")
        self.visit(node.expression)
        self._write(") ")
        self.visit(node.matcher)

    def visitThrowExpression(self, node):
        self._write("throw ")
        self.visit(node.exception)

    def visitTryCatchExpression(self, node):
        self._write("try ")
        self.visit(node.expression)
        if node.catchHandler:
            self._writeHanging("catch ")
            assert isinstance(node.catchHandler, ast.PartialFunctionExpression)
            simpleCatch = (len(node.catchHandler.cases) == 1 and
                           node.catchHandler.cases[0].condition is None)
            if simpleCatch:
                self._write("(")
                self.visit(node.catchHandler.cases[0].pattern)
                self._write(") ")
                self.visit(node.catchHandler.cases[0].expression)
            else:
                self.visit(node.catchHandler)
        if node.finallyHandler:
            self._writeHanging("finally ")
            self.visit(node.finallyHandler)

    def visitLambdaExpression(self, node):
        self._write("lambda ")
        self._writeParameters(node.parameters)
        if node.parameters:
            self._write(" ")
        self.visit(node.body)

    def visitReturnExpression(self, node):
        self._write("return")
        if node.expression:
            self._write(" ")
            self.visit(node.expression)

    def visitGroupExpression(self, node):
        self._write("(")
        self.visit(node.expression)
        self._write(")")

    def visitUnitLiteral(self, node):
        self._write("()")

    def visitIntegerLiteral(self, node):
        self._write(node.text)

    def visitFloatLiteral(self, node):
        self._write(node.text)

    def visitBooleanLiteral(self, node):
        self._write("true" if node.value else "false")

    def visitNullLiteral(self, node):
        self._write("null")

    def visitStringLiteral(self, node):
        self._write(utils.encodeString(node.value))

    def visitCommentGroup(self, node):
        # We should only visit standalone comment groups, not comments attached to a node.
        if len(node.before) > 0:
            for comment in node.before[:-1]:
                self.visit(comment)
                self._endl()
            self.visit(node.before[-1])

    def visitBlankLine(self, node):
        # BlankLine should only occur in a list of statements, and _writeStatements adds
        # newlines between elements, so we don't need to do anything here.
        pass

    def visitComment(self, node):
        self._write(node.text)

    def preVisit(self, node):
        if isinstance(node, ast.CommentedNode):
            for comment in node.comments.before:
                self.visitComment(comment)
                self._endl()

    def postVisit(self, node):
        if isinstance(node, ast.CommentedNode) and len(node.comments.after) > 0:
            assert len(node.comments.after) == 1
            self._write(' ' * self._fmt.spacesBeforeTailComment)
            self.visitComment(node.comments.after[0])

    def _writeAttributes(self, attribs):
        self._writeList(attribs, "", " ", " ")

    def _writeTypeParameters(self, typeParameters):
        self._writeList(typeParameters, "[", ", ", "]")

    def _writeParameters(self, parameters, writeNone=False, writeEmpty=False):
        self._writeList(parameters, "(", ", ", ")", writeNone=writeNone, writeEmpty=writeEmpty)

    def _writeTypeArguments(self, typeArgs):
        self._writeList(typeArgs, "[", ", ", "]")

    def _writeArguments(self, args):
        self._writeList(args, "(", ", ", ")", writeEmpty=True)

    def _writeTypeFlags(self, flags):
        utils.each(self._write, flags)

    def _writePrefix(self, prefix):
        if not prefix:
            return
        for component in prefix:
            self.visit(component)
            self._write(".")

    def _writeStatements(self, stmts):
        first = True
        prevWasImport = False
        prevWasVar = False
        prevWasShortFunc = False
        prevWasDefn = False
        prevWasStmt = False
        prevWasCase = False
        for stmt in stmts:
            if isinstance(stmt, ast.BlankLine):
                if self._preserveBlanks:
                    self._endl()
                continue

            isImport = isinstance(stmt, ast.ImportStatement)
            isVar = isinstance(stmt, ast.VariableDefinition)
            isShortFunc = (isinstance(stmt, ast.FunctionDefinition) and
                           len(stmt.comments.before) == 0 and
                           (stmt.body is None or
                            not isinstance(stmt.body, ast.BlockExpression)))
            isDefn = isinstance(stmt, ast.Definition)
            isStmt = (isinstance(stmt, ast.VariableDefinition) or
                      isinstance(stmt, ast.Expression))
            isCase = isinstance(stmt, ast.PartialFunctionCase)

            if not first:
                self._endl()
                if prevWasImport and isImport:
                    linesBetween = self._fmt.linesBetweenImports
                elif prevWasVar and isVar:
                    linesBetween = self._fmt.linesBetweenVars
                elif prevWasShortFunc and isShortFunc:
                    linesBetween = self._fmt.linesBetweenShortFuncs
                elif isDefn and prevWasDefn:
                    if self._currentIndent > 0:
                        linesBetween = self._fmt.linesBetweenInnerDefns
                    else:
                        linesBetween = self._fmt.linesBetweenTopDefns
                elif ((isStmt and prevWasStmt) or
                      (isCase and prevWasCase)):
                    linesBetween = 0
                else:
                    linesBetween = self._fmt.linesBetweenMisc
                for _ in xrange(linesBetween - self._blank):
                    self._endl()
            first = False
            prevWasImport = isImport
            prevWasVar = isVar
            prevWasShortFunc = isShortFunc
            prevWasDefn = isDefn
            prevWasStmt = isStmt
            prevWasCase = isCase

            self.visit(stmt)

    def _writeBlock(self, nodes):
        if nodes is None or len(nodes) == 0:
            return
        self._endl()
        self._indent()
        self._writeStatements(nodes)
        self._dedent()

    def _writeList(self, nodes, begin, sep, end, writeNone=False, writeEmpty=False):
        if (nodes is None and not writeNone or
            len(nodes) == 0 and not writeEmpty):
            return
        self._write(begin)
        _sep = ""
        for node in nodes:
            self._write(_sep)
            _sep = sep
            self.visit(node)
        self._write(end)

    def _writeHanging(self, s):
        if self._hanging:
            self._endl()
            self._hanging = False
        else:
            self._write(" ")
        self._write(s)

    def _write(self, s):
        assert isinstance(s, str) or isinstance(s, unicode)
        if self._begin:
            self._line.append(" " * self._currentIndent)
            self._begin = False
        self._line.append(s)
        self._hanging = False

    def _indent(self):
        self._currentIndent += self._fmt.indentWidth

    def _dedent(self):
        self._currentIndent -= self._fmt.indentWidth
        self._hanging = True

    def _endl(self):
        self._flush()
        self._out.write("\n")
        if self._begin:
            self._blank += 1
        else:
            self._blank = 0
            self._begin = True

    def _flush(self):
        if len(self._line) > 0:
            self._line[-1] = self._line[-1].rstrip()
        for s in self._line:
            self._out.write(s)
        del self._line[:]


class _PreserveBlanksScope(object):
    def __init__(self, visitor):
        self._visitor = visitor
        self._oldPreserveBlanks = visitor._preserveBlanks

    def __enter__(self):
        self._visitor._preserveBlanks = True

    def __exit__(self, *unused):
        self._visitor._preserveBlanks = self._oldPreserveBlanks
