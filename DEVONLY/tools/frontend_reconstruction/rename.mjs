// Rename local variables of one function, keeping the file's formatting.
// usage: node rename.mjs <file> <functionName> old=new [old=new ...]
import fs from "fs";
import { parse } from "@babel/parser";
import traverseMod from "@babel/traverse";
const traverse = traverseMod.default?.default ?? traverseMod.default ?? traverseMod;
const [file, fname, ...pairs] = process.argv.slice(2);
const map = Object.fromEntries(pairs.map((p) => p.split("=")));
let src = fs.readFileSync(file, "utf8");
const ast = parse(src, { sourceType: "module", plugins: ["jsx", "typescript"] });
const edits = [];
let found = false;
traverse(ast, {
  Function(path) {
    const id = path.node.id?.name;
    if (id !== fname) return;
    found = true;
    for (const [old, neu] of Object.entries(map)) {
      const b = path.scope.getOwnBinding(old);
      if (!b) { console.error(`no binding ${old} in ${fname}`); process.exitCode = 1; continue; }
      if (path.scope.hasBinding(neu) || Object.values(map).filter((v) => v === neu).length > 1) {
        let clash = path.scope.getBinding(neu); if (clash && !map[neu]) { console.error(`name ${neu} already used`); process.exitCode = 1; continue; }
      }
      const ids = [b.identifier, ...b.referencePaths.map((r) => r.node), ...b.constantViolations.flatMap((c) => Object.values(c.getBindingIdentifiers()).filter((n) => n.name === old))];
      const parents = new Map();
      for (const r of b.referencePaths) parents.set(r.node, r.parentPath);
      for (const n of new Set(ids)) {
        const parent = parents.get(n);
        if (parent && parent.isObjectProperty() && parent.node.shorthand && parent.node.value === n) {
          edits.push([n.start, n.end, `${old}: ${neu}`]);
        } else edits.push([n.start, n.end, neu]);
      }
    }
    path.stop();
  },
});
if (!found) { console.error(`function ${fname} not found`); process.exit(1); }
edits.sort((a, b) => b[0] - a[0]);
for (const [s, e, t] of edits) src = src.slice(0, s) + t + src.slice(e);
fs.writeFileSync(file, src);
console.log(`${fname}: ${edits.length} edits`);
