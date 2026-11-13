// List identifiers used in the app part but not declared there (= what must be imported).
import fs from "node:fs";
import { parse } from "@babel/parser";
import _traverse from "@babel/traverse";
const traverse = _traverse.default ?? _traverse;
const ast = parse(fs.readFileSync(process.argv[2], "utf8"), { sourceType: "module", plugins: ["jsx"] });
const free = new Map();
traverse(ast, {
  Program(path) {
    for (const [name, refs] of Object.entries(path.scope.globals ?? {})) free.set(name, 0);
    const g = path.scope.getProgramParent();
    // babel collects undeclared references in scope.globals
    for (const name of Object.keys(g.globals)) free.set(name, (free.get(name) ?? 0));
  },
  "Identifier|JSXIdentifier"(path) {
    const n = path.node.name;
    if (free.has(n)) free.set(n, free.get(n) + 1);
  },
});
const builtins = new Set(Object.getOwnPropertyNames(globalThis).concat(["document","window","navigator","localStorage","crypto","structuredClone","React","Icon","undefined","console","fetch","URL","Blob","FileReader","setTimeout","clearTimeout","setInterval","clearInterval","requestAnimationFrame","cancelAnimationFrame","HTMLElement","Node","Event","CustomEvent","AbortController","TextDecoder","FormData","Intl","Promise","Math","JSON","Date","Array","Object","Number","String","Boolean","Set","Map","Error","RegExp","encodeURIComponent","decodeURIComponent","isNaN","parseInt","parseFloat","queueMicrotask","matchMedia","getComputedStyle","ResizeObserver","IntersectionObserver","MutationObserver","location","history","alert","confirm","performance","Symbol","WeakMap","Infinity","NaN","globalThis","Reflect","Proxy","escape","atob","btoa","EventSource","Response","Request","Headers","KeyboardEvent","MouseEvent","Element","HTMLInputElement","HTMLTextAreaElement","DOMParser","Image","Audio","navigator"]));
console.log([...free.entries()].filter(([n]) => !builtins.has(n)).sort((a,b)=>b[1]-a[1]).map(([n,c])=>`${n}:${c}`).join(" "));
