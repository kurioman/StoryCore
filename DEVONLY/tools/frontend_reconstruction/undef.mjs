import fs from "node:fs"; import path from "node:path";
import { parse } from "@babel/parser"; import _traverse from "@babel/traverse";
const traverse = _traverse.default ?? _traverse;
const G = new Set(Object.getOwnPropertyNames(globalThis).concat(["document","window","navigator","localStorage","sessionStorage","structuredClone","console","fetch","URL","Blob","FileReader","HTMLElement","Node","Event","CustomEvent","AbortController","TextDecoder","FormData","matchMedia","getComputedStyle","ResizeObserver","IntersectionObserver","MutationObserver","location","history","alert","confirm","performance","requestAnimationFrame","cancelAnimationFrame","EventSource","KeyboardEvent","MouseEvent","Element","HTMLInputElement","HTMLTextAreaElement","DOMParser","Image","CSS","getSelection","innerWidth","innerHeight","scrollTo","open","print","self","prompt","setTimeout","clearTimeout","setInterval","clearInterval","queueMicrotask","crypto","Intl","undefined","arguments"]));
function walk(d){ return fs.readdirSync(d,{withFileTypes:true}).flatMap(e=> e.isDirectory()? walk(path.join(d,e.name)) : /\.jsx?$/.test(e.name)? [path.join(d,e.name)] : []); }
for (const f of walk(process.argv[2])) {
  const ast = parse(fs.readFileSync(f,"utf8"),{sourceType:"module",plugins:["jsx"]});
  const miss = new Set();
  traverse(ast,{ Program(p){ for (const n of Object.keys(p.scope.globals)) if(!G.has(n)) miss.add(n); },
    JSXOpeningElement(p){ const n=p.node.name; if(n.type==="JSXIdentifier" && /^[a-z]/.test(n.name)===false && !p.scope.hasBinding(n.name)) miss.add("<"+n.name+">"); if(n.type==="JSXIdentifier" && /^[a-z]{1,2}[A-Z_$]|^[a-z]{1,2}$/.test(n.name) && !["a","b","i","p","q","s","u","em","h1","h2","h3","h4","h5","h6","li","ol","ul","tr","td","th","hr","br","dl","dt","dd","rt","rp"].includes(n.name)) miss.add("<"+n.name+"?>"); } });
  if (miss.size) console.log(path.relative(process.argv[2],f), [...miss].join(" "));
}
