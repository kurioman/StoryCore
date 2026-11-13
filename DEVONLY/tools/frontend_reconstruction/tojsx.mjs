// Turn compiled React calls `(0, h.jsx)(type, {props, children})` back into JSX, and rename lucide icon variables,
// so the old bundle can be read and ported by hand. Output is a reading aid, not shipped code.
import fs from "node:fs";
import { parse } from "@babel/parser";
import _traverse from "@babel/traverse";
import _generate from "@babel/generator";
import * as t from "@babel/types";
const traverse = _traverse.default ?? _traverse, generate = _generate.default ?? _generate;

const src = fs.readFileSync(process.argv[2], "utf8");
const icons = JSON.parse(fs.readFileSync("/root/iconmap.json", "utf8"));
const ast = parse(src, { sourceType: "module", errorRecovery: true, plugins: ["jsx"] });

function isJsxCall(callee) {
  // (0, h.jsx) or (0, h.jsxs) -> SequenceExpression [0, MemberExpression h.jsx]
  if (t.isSequenceExpression(callee)) callee = callee.expressions[callee.expressions.length - 1];
  return t.isMemberExpression(callee) && t.isIdentifier(callee.property) && /^jsxs?$/.test(callee.property.name) &&
    t.isIdentifier(callee.object, { name: "h" });
}
function isFragment(node) {
  return t.isMemberExpression(node) && t.isIdentifier(node.object, { name: "h" }) && t.isIdentifier(node.property, { name: "Fragment" });
}
function nameFor(node) {
  if (t.isStringLiteral(node)) return t.jsxIdentifier(node.value);
  if (t.isTemplateLiteral(node) && node.expressions.length === 0) return t.jsxIdentifier(node.quasis[0].value.cooked);
  if (t.isIdentifier(node)) return t.jsxIdentifier(Object.hasOwn(icons, node.name) ? `Icon.${icons[node.name]}` : /^[a-z_$]/.test(node.name) ? `$$V_${node.name}` : node.name);
  if (t.isMemberExpression(node) && !node.computed) return t.jsxMemberExpression(
    t.isIdentifier(node.object) ? t.jsxIdentifier(node.object.name) : nameFor(node.object), t.jsxIdentifier(node.property.name));
  return null;
}
function childNode(c) {
  if (t.isJSXElement(c) || t.isJSXFragment(c)) return c;
  if (t.isStringLiteral(c)) return t.jsxText(c.value);
  if (t.isTemplateLiteral(c) && c.expressions.length === 0) {
    const v = c.quasis[0].value.cooked;
    return /[{}<>]/.test(v) || /^\s|\s$/.test(v) ? t.jsxExpressionContainer(t.stringLiteral(v)) : t.jsxText(v);
  }
  return t.jsxExpressionContainer(c);
}
traverse(ast, {
  CallExpression: { exit(path) {
    const { callee, arguments: args } = path.node;
    if (!isJsxCall(callee) || args.length < 2) return;
    const [type, props, key] = args;
    const frag = isFragment(type);
    const name = frag ? null : nameFor(type);
    if (!frag && !name) return;
    if (!t.isObjectExpression(props)) return;
    const attrs = []; let children = [];
    for (const p of props.properties) {
      if (t.isSpreadElement(p)) { attrs.push(t.jsxSpreadAttribute(p.argument)); continue; }
      if (!t.isObjectProperty(p) || p.computed) return;
      const k = t.isIdentifier(p.key) ? p.key.name : t.isStringLiteral(p.key) ? p.key.value : null;
      if (k == null) return;
      if (k === "children") {
        children = t.isArrayExpression(p.value) ? p.value.elements.filter(Boolean).map(childNode) : [childNode(p.value)];
        continue;
      }
      let v = p.value;
      if (t.isBooleanLiteral(v, { value: true }) || (t.isUnaryExpression(v, { operator: "!" }) && t.isNumericLiteral(v.argument, { value: 0 }))) { attrs.push(t.jsxAttribute(t.jsxIdentifier(k), null)); continue; }
      if (t.isUnaryExpression(v, { operator: "!" }) && t.isNumericLiteral(v.argument, { value: 1 })) v = t.booleanLiteral(false);
      const val = t.isStringLiteral(v) ? v : (t.isTemplateLiteral(v) && v.expressions.length === 0 && !/["\n]/.test(v.quasis[0].value.cooked))
        ? t.stringLiteral(v.quasis[0].value.cooked) : t.jsxExpressionContainer(v);
      attrs.push(t.jsxAttribute(t.jsxIdentifier(k), val));
    }
    if (key) attrs.push(t.jsxAttribute(t.jsxIdentifier("key"), t.jsxExpressionContainer(key)));
    if (frag) { path.replaceWith(t.jsxFragment(t.jsxOpeningFragment(), t.jsxClosingFragment(), children)); return; }
    const selfClosing = children.length === 0;
    path.replaceWith(t.jsxElement(t.jsxOpeningElement(name, attrs, selfClosing), selfClosing ? null : t.jsxClosingElement(name), children, selfClosing));
  } },
  // boolean literals !0 / !1 elsewhere
  UnaryExpression(path) {
    const n = path.node;
    if (n.operator === "!" && t.isNumericLiteral(n.argument) && (n.argument.value === 0 || n.argument.value === 1))
      path.replaceWith(t.booleanLiteral(n.argument.value === 0));
    else if (n.operator === "void" && t.isNumericLiteral(n.argument, { value: 0 })) path.replaceWith(t.identifier("undefined"));
  },
  // (0, m.useState) -> React.useState
  SequenceExpression(path) {
    const ex = path.node.expressions;
    if (ex.length === 2 && t.isNumericLiteral(ex[0], { value: 0 }) && t.isMemberExpression(ex[1]) && t.isIdentifier(ex[1].object)) {
      const obj = ex[1].object.name;
      if (obj === "m") path.replaceWith(t.memberExpression(t.identifier("React"), ex[1].property));
    }
  },
  Identifier(path) {
    if (Object.hasOwn(icons, path.node.name) && path.parentPath.isExpression() && !path.parentPath.isMemberExpression({ property: path.node })) {
      path.node.name = `Icon.${icons[path.node.name]}`;
    }
  },
});
fs.writeFileSync(process.argv[3], generate(ast, { retainLines: false, jsescOption: { minimal: true } }).code);
