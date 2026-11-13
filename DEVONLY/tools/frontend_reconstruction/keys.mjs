// Collect every literal key passed to msg(...) in src -> sorted JSON object {key: key}
import fs from "node:fs"; import path from "node:path";
import { parse } from "@babel/parser"; import _traverse from "@babel/traverse";
const traverse = _traverse.default ?? _traverse;
function walk(d){ return fs.readdirSync(d,{withFileTypes:true}).flatMap(e=> e.isDirectory()? walk(path.join(d,e.name)) : /\.(jsx?|tsx?)$/.test(e.name) && !e.name.endsWith(".d.ts") ? [path.join(d,e.name)] : []); }
const keys = new Set(), dyn = [];
for (const f of walk(process.argv[2])) {
  const ast = parse(fs.readFileSync(f,"utf8"),{sourceType:"module",plugins: f.endsWith(".ts") ? ["typescript"] : f.endsWith(".tsx") ? ["typescript","jsx"] : ["jsx"]});
  traverse(ast,{ CallExpression(p){ const c=p.node.callee; if(c.type!=="Identifier"||c.name!=="msg") return; const a=p.node.arguments[0];
    if(a?.type==="StringLiteral") keys.add(a.value); else if (a?.type==="TemplateLiteral" && !a.expressions.length) keys.add(a.quasis[0].value.cooked); else dyn.push(path.relative(process.argv[2],f)+":"+p.node.loc.start.line); } });
}
fs.writeFileSync(process.argv[3], JSON.stringify(Object.fromEntries([...keys].sort().map(k=>[k,k])), null, 2)+"\n");
console.log("keys", keys.size, "dynamic calls", dyn.length); console.log(dyn.join(" "));
