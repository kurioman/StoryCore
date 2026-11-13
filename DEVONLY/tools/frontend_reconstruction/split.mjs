// Rebuild readable source modules from the decompiled bundle (app.cut.jsx):
//  1. rename top-level bindings (names.json) and library references (FREE map)
//  2. rename short local aliases of destructured props / hook results to meaningful names
//  3. wrap user-visible English text in t("...") for i18n (collected into en.json)
//  4. split by line ranges into modules with generated imports/exports
import fs from "node:fs";
import path from "node:path";
import { parse } from "@babel/parser";
import _traverse from "@babel/traverse";
import _generate from "@babel/generator";
import * as t from "@babel/types";
const traverse = _traverse.default ?? _traverse, generate = _generate.default ?? _generate;

const OUT = process.argv[3];
const src = fs.readFileSync(process.argv[2], "utf8").replace("/*__LIB_CUT__*/", "");
const names = JSON.parse(fs.readFileSync("/root/decomp/names.json", "utf8"));
const icons = JSON.parse(fs.readFileSync("/root/iconmap.json", "utf8"));

// library / api-layer identifiers the app part uses without declaring them
const FREE = {
  m: ["React", "react", "ns"], h: ["React", "react", "ns"],
  _: ["useQueryClient", "@tanstack/react-query"], A: ["useQuery", "@tanstack/react-query"],
  j: ["useMutation", "@tanstack/react-query"], Ye: ["QueryClient", "@tanstack/react-query"],
  ct: ["useIsMutating", "@tanstack/react-query"], ut: ["useMutationState", "@tanstack/react-query"],
  N: ["apiGet", "@/api/legacy"], P: ["apiPost", "@/api/legacy"], vi: ["apiPut", "@/api/legacy"],
  yi: ["apiPatch", "@/api/legacy"], bi: ["apiDelete", "@/api/legacy"], xi: ["apiUpload", "@/api/legacy"],
  Si: ["apiStream", "@/api/legacy"], F: ["errorMessage", "@/api/legacy"], mi: ["ApiError", "@/api/legacy"],
  H: ["queryKeys", "@/api/queries"], vp: ["useStories", "@/api/queries"], yp: ["useStory", "@/api/queries"],
  bp: ["useMessages", "@/api/queries"], xp: ["useStoryState", "@/api/queries"], Sp: ["useCast", "@/api/queries"],
  Cp: ["useContextPreview", "@/api/queries"], wp: ["useProviders", "@/api/queries"], Tp: ["useSettings", "@/api/queries"],
  Ep: ["useCommands", "@/api/queries"], Dp: ["useWorlds", "@/api/queries"], Op: ["useAvatars", "@/api/queries"],
  kp: ["useReviewCount", "@/api/queries"], Ap: ["useInvalidateStory", "@/api/queries"], _p: ["EXPRESSIONS", "@/api/queries"],
  gp: ["streamEventSchema", "@/api/queries"], jp: ["ErrorBoundary", "@/components/ErrorBoundary"],
  v: ["QueryClientProvider", "@tanstack/react-query"], qx: ["clsx", "clsx"], pi: ["ReactDOMClient", "react-dom/client", "ns"],
  sj: ["ReactMarkdown", "react-markdown", "default"], OP: ["remarkGfm", "remark-gfm", "default"],
  u_: ["Dialog.Root", "@radix-ui/react-dialog", "nsmember"], m_: ["Dialog.Portal", "@radix-ui/react-dialog", "nsmember"],
  g_: ["Dialog.Overlay", "@radix-ui/react-dialog", "nsmember"], b_: ["Dialog.Content", "@radix-ui/react-dialog", "nsmember"],
  w_: ["Dialog.Title", "@radix-ui/react-dialog", "nsmember"], T_: ["Dialog.Description", "@radix-ui/react-dialog", "nsmember"],
  D_: ["Dialog.Close", "@radix-ui/react-dialog", "nsmember"],
  _b: ["PopoverPrimitive.Root", "@radix-ui/react-popover", "nsmember"], yb: ["PopoverPrimitive.Trigger", "@radix-ui/react-popover", "nsmember"],
  Cb: ["PopoverPrimitive.Portal", "@radix-ui/react-popover", "nsmember"], Tb: ["PopoverPrimitive.Content", "@radix-ui/react-popover", "nsmember"],
  Lx: ["TabsPrimitive.Root", "@radix-ui/react-tabs", "nsmember"], zx: ["TabsPrimitive.List", "@radix-ui/react-tabs", "nsmember"],
  Vx: ["TabsPrimitive.Trigger", "@radix-ui/react-tabs", "nsmember"], Ux: ["TabsPrimitive.Content", "@radix-ui/react-tabs", "nsmember"],
  B: ["z.string", "zod", "z"], V: ["z.object", "zod", "z"], Of: ["z.array", "zod", "z"], gf: ["z.number", "zod", "z"],
  bf: ["z.boolean", "zod", "z"], Rf: ["z.record", "zod", "z"], Bf: ["z.enum", "zod", "z"], wf: ["z.unknown", "zod", "z"],
  Hf: ["z.literal", "zod", "z"], Pf: ["z.discriminatedUnion", "zod", "z"], Sf: ["z.any", "zod", "z"],
};
const NS_NAMES = { "@radix-ui/react-dialog": "Dialog", "@radix-ui/react-popover": "PopoverPrimitive", "@radix-ui/react-tabs": "TabsPrimitive" };

// module of each top-level statement, by start line in app.cut.jsx
const RANGES = [
  ["U", "lib/util"], ["tS", "lib/router"], ["aS", "lib/hooks"], ["sS", "lib/util"], ["lS", "components/ui"],
  ["MS", "features/avatars/AvatarsPage"], ["RS", "features/commands/CommandsPage"], ["VS", "features/help/HelpDialog"],
  ["GS", "features/sidebar/Sidebar"], ["XS", "features/home/HomePage"], ["ZS", "features/lore/schemas"],
  ["iC", "features/story/stateEditor"], ["oC", "lib/portraits"], ["cC", "features/lore/LorePage"],
  ["vC", "features/portraits/PortraitsPage"], ["wC", "features/settings/OllamaModels"], ["EC", "features/settings/Providers"],
  ["XC", "features/settings/SettingsPage"], ["$C", "features/settings/NarrationSettings"], ["tw", "features/settings/MemorySettings"],
  ["nw", "features/settings/GlobalNoteSettings"], ["rw", "features/settings/AppearanceSettings"], ["iw", "features/settings/DataSettings"],
  ["aw", "features/story/api"], ["kP", "features/story/prose"], ["UP", "features/story/chrono"], ["YP", "features/story/dialogs"],
  ["oF", "features/story/panels/KnownPanel"], ["dF", "features/story/panels/StatusPanel"], ["SF", "features/story/panels/RelationsPanel"],
  ["DF", "features/story/panels/CastPanel"], ["AF", "features/story/panels/ItemsQuests"], ["MF", "features/story/journal"],
  ["ZF", "features/story/composer"], ["oI", "features/story/transcript"], ["wI", "features/story/header"],
  ["NI", "features/story/StoryPage"], ["BI", "features/wizard/NewStoryWizard"], ["GI", "app/App"],
];
const MARKERS = new Map(RANGES.map(([n, m]) => [names[n] ?? n, m]));

const ast = parse(src, { sourceType: "module", plugins: ["jsx"] });

// ---------- 0. lowercase JSX tags that are really variables (decompiled `jsx(q, …)` became `<q>`)
{
  const jsxRefs = new Map(); // binding -> [JSXIdentifier nodes]
  traverse(ast, { JSXIdentifier(p) {
    if (!(p.parentPath.isJSXOpeningElement({ name: p.node }) || p.parentPath.isJSXClosingElement({ name: p.node }))) return;
    if (!p.node.name.startsWith("$$V_")) return;
    const n = p.node.name.slice(4);
    p.node.name = n;
    const b = p.scope.getBinding(n);
    if (!b) return;
    if (!jsxRefs.has(b)) jsxRefs.set(b, []);
    jsxRefs.get(b).push(p.node);
  } });
  for (const [b, nodes] of jsxRefs) {
    let to;
    if (b.scope.path.isProgram()) to = names[b.identifier.name] ?? ("C_" + b.identifier.name);
    else {
      const parent = b.path.parentPath;
      let key = null;
      if (b.path.isObjectProperty?.()) key = b.path.node.key.name;
      const prop = b.identifier && b.path.findParent?.((x) => x.isObjectProperty());
      if (prop && t.isIdentifier(prop.node.key)) key = prop.node.key.name;
      to = key ? key[0].toUpperCase() + key.slice(1) : "Comp" + b.identifier.name.toUpperCase();
      b.scope.rename(b.identifier.name, to);
    }
    for (const n of nodes) n.name = to;
  }
}

// ---------- 1. renames
const i18n = new Map(); // key -> english text
const program = (() => { let p; traverse(ast, { Program(x) { p = x; x.stop(); } }); return p; })();
for (const [from, to] of Object.entries(names)) if (program.scope.hasOwnBinding(from)) program.scope.rename(from, to);

function freeReplacement(name) {
  const f = FREE[name];
  if (f) return f[0];
  if (Object.hasOwn(icons, name)) return `Icon.${icons[name]}`;
  return null;
}
const usedImports = new Map(); // module -> Set(specifier)
traverse(ast, {
  Identifier(p) {
    const n = p.node.name;
    if (p.scope.hasBinding(n)) return;
    if (p.parentPath.isMemberExpression({ property: p.node }) && !p.parent.computed) return;
    if (p.parentPath.isObjectProperty({ key: p.node }) && !p.parent.computed) return;
    if (p.parentPath.isObjectMethod({ key: p.node })) return;
    const rep = freeReplacement(n);
    if (!rep) return;
    const parts = rep.split(".");
    let node = t.identifier(parts[0]);
    for (const q of parts.slice(1)) node = t.memberExpression(node, t.identifier(q));
    p.replaceWith(node);
    p.skip();
  },
  JSXIdentifier(p) {
    const n = p.node.name;
    if (p.parentPath.isJSXAttribute()) return;
    if (p.parentPath.isJSXMemberExpression({ property: p.node })) return;
    if (p.scope.hasBinding(n)) return;
    const rep = freeReplacement(n);
    if (!rep) return;
    const parts = rep.split(".");
    if (parts.length === 1) { p.node.name = rep; return; }
    let node = t.jsxIdentifier(parts[0]);
    for (const q of parts.slice(1)) node = t.jsxMemberExpression(node, t.jsxIdentifier(q));
    p.replaceWith(node);
  },
});

// ---------- 2. local aliases: { prop: e } -> { prop }, const e = useFoo() -> foo
const RESERVED = new Set(["default", "class", "function", "new", "delete", "in", "for", "if", "do", "var", "let", "const", "return", "switch", "case", "this", "typeof", "void", "with", "yield", "await", "enum", "export", "import", "super", "catch", "try", "finally", "throw", "while", "break", "continue", "debugger", "instanceof", "null", "true", "false", "undefined", "msg", "cn", "React", "Icon", "z"]);
function nameFree(scope, name) {
  if (RESERVED.has(name) || /^[A-Z]/.test(name)) return false;
  // nobody in this scope chain or inside the scope's block may use that name
  if (scope.hasBinding(name) || scope.hasGlobal(name)) return false;
  let clash = false;
  scope.path.traverse({ Identifier(p) {
    if (p.node.name !== name) return;
    if (p.parentPath.isMemberExpression({ property: p.node }) && !p.parent.computed) return;
    if ((p.parentPath.isObjectProperty({ key: p.node }) || p.parentPath.isObjectMethod({ key: p.node })) && !p.parent.computed && !p.parent.shorthand) return;
    clash = true; p.stop();
  } });
  return !clash;
}
function tryRename(scope, from, to) {
  if (from === to || from.length > 2) return;
  if (!scope.hasOwnBinding(from)) return;
  if (!nameFree(scope, to)) return;
  scope.rename(from, to);
}
traverse(ast, {
  ObjectPattern(p) {
    for (const prop of p.node.properties) {
      if (!t.isObjectProperty(prop) || prop.computed) continue;
      const key = t.isIdentifier(prop.key) ? prop.key.name : null;
      let val = prop.value;
      if (t.isAssignmentPattern(val)) val = val.left;
      if (key && t.isIdentifier(val) && val.name !== key) {
        const b = p.scope.getBinding(val.name);
        if (b) tryRename(b.scope, val.name, key);
      }
    }
  },
  VariableDeclarator(p) {
    const id = p.node.id, init = p.node.init;
    if (!t.isIdentifier(id) || id.name.length > 2 || !t.isCallExpression(init)) return;
    let callee = init.callee;
    let base = null;
    if (t.isIdentifier(callee)) {
      const c = callee.name;
      if (c === "useQueryClient") base = "queryClient";
      else if (/^use[A-Z]/.test(c)) base = c[3].toLowerCase() + c.slice(4);
    }
    if (!base) return;
    tryRename(p.scope, id.name, base);
  },
});
// ObjectPattern rename shortens `{ prop: prop }` to `{ prop }`
traverse(ast, { ObjectProperty(p) {
  if (!p.node.computed && t.isIdentifier(p.node.key) && t.isIdentifier(p.node.value) && p.node.key.name === p.node.value.name) p.node.shorthand = true;
  if (!p.node.computed && t.isIdentifier(p.node.key) && t.isAssignmentPattern(p.node.value) && t.isIdentifier(p.node.value.left, { name: p.node.key.name })) p.node.shorthand = true;
} });

// ---------- 3. i18n
const TEXT_ATTRS = new Set(["label", "title", "placeholder", "aria-label", "description", "hint", "confirmLabel", "alt"]);
const TEXT_KEYS = new Set(["label", "title", "body", "hint", "description", "confirmLabel", "placeholder", "short", "a", "q"]);
const looksText = (s) => /[A-Za-z]{2}/.test(s) && !/\{\{/.test(s) && !/^[a-z0-9_.:/#-]+$/.test(s.trim()) && !/^(https?:|\/api|#\/|\/)/.test(s.trim())
  && !/\b(px|rem|flex|grid|rounded|border|text-|bg-|w-\d|h-\d)\b/.test(s) && !/^[a-z]+(-[a-z0-9]+)+$/.test(s.trim());
const tCall = (text, vars) => {
  const key = text;
  i18n.set(key, text);
  const args = [t.stringLiteral(key)];
  if (vars && vars.length) args.push(t.objectExpression(vars.map((v, i) => t.objectProperty(t.identifier(`v${i}`), v))));
  return t.callExpression(t.identifier("msg"), args);
};
function templateToT(tl) {
  let text = "";
  const vars = [];
  tl.quasis.forEach((q, i) => {
    text += q.value.cooked;
    if (i < tl.expressions.length) { text += `{{v${vars.length}}}`; vars.push(tl.expressions[i]); }
  });
  return { text, vars };
}
function toT(node) {
  if (t.isStringLiteral(node) && looksText(node.value)) return tCall(node.value);
  if (t.isTemplateLiteral(node)) {
    const { text, vars } = templateToT(node);
    const plain = text.replace(/\{\{v\d+\}\}/g, "");
    if (looksText(plain) && plain.trim().length > 1) return tCall(text, vars);
  }
  return null;
}
const filesUsingT = new Set();
traverse(ast, {
  JSXText(p) {
    const raw = p.node.value;
    if (!/[A-Za-z]{2}/.test(raw) || /\{\{/.test(raw)) return;
    const lead = raw.match(/^\s*/)[0], trail = raw.match(/\s*$/)[0];
    const core = raw.trim().replace(/\s+/g, " ");
    const nodes = [];
    if (lead && !/\n/.test(lead)) nodes.push(t.jsxExpressionContainer(t.stringLiteral(" ")));
    nodes.push(t.jsxExpressionContainer(tCall(core)));
    if (trail && !/\n/.test(trail)) nodes.push(t.jsxExpressionContainer(t.stringLiteral(" ")));
    p.replaceWithMultiple(nodes);
    p.skip();
  },
  JSXExpressionContainer(p) {
    // {" Done"} / {`Done`} children
    if (!p.parentPath.isJSXElement() && !p.parentPath.isJSXFragment()) return;
    const e = p.node.expression;
    if (t.isStringLiteral(e) && /[A-Za-z]{2}/.test(e.value) && !/\{\{/.test(e.value)) {
      const lead = e.value.match(/^\s*/)[0], trail = e.value.match(/\s*$/)[0];
      const nodes = [];
      if (lead) nodes.push(t.jsxExpressionContainer(t.stringLiteral(" ")));
      nodes.push(t.jsxExpressionContainer(tCall(e.value.trim())));
      if (trail) nodes.push(t.jsxExpressionContainer(t.stringLiteral(" ")));
      p.replaceWithMultiple(nodes); p.skip(); return;
    }
    const r = toT(e); if (r) { p.node.expression = r; p.skip(); return; }
    const walk = (x) => {
      if (t.isConditionalExpression(x)) {
        const a = toT(x.consequent); if (a) x.consequent = a; else walk(x.consequent);
        const b = toT(x.alternate); if (b) x.alternate = b; else walk(x.alternate);
      } else if (t.isLogicalExpression(x)) {
        const b = toT(x.right); if (b) x.right = b; else walk(x.right);
      }
    };
    walk(e);
  },
  JSXAttribute(p) {
    const name = t.isJSXIdentifier(p.node.name) ? p.node.name.name : "";
    if (!TEXT_ATTRS.has(name) || !p.node.value) return;
    const v = p.node.value;
    if (t.isStringLiteral(v) && looksText(v.value)) { p.node.value = t.jsxExpressionContainer(tCall(v.value)); return; }
    if (t.isJSXExpressionContainer(v)) {
      const r = toT(v.expression); if (r) v.expression = r;
      else if (t.isConditionalExpression(v.expression)) {
        const c = v.expression; const a = toT(c.consequent), b = toT(c.alternate);
        if (a) c.consequent = a; if (b) c.alternate = b;
      }
    }
  },
  ObjectProperty(p) {
    if (p.node.computed) return;
    const key = t.isIdentifier(p.node.key) ? p.node.key.name : t.isStringLiteral(p.node.key) ? p.node.key.value : "";
    if (!TEXT_KEYS.has(key)) return;
    if (p.parentPath.parentPath.isCallExpression() && t.isMemberExpression(p.parentPath.parent.callee)) return; // z.object({...}) etc
    const r = toT(p.node.value); if (r) p.node.value = r;
  },
  CallExpression(p) {
    const c = p.node.callee;
    if (t.isIdentifier(c, { name: "toast" }) && p.node.arguments.length) {
      const r = toT(p.node.arguments[0]); if (r) p.node.arguments[0] = r;
    }
    if (t.isIdentifier(c, { name: "Error" })) return;
  },
});

// ---------- 4. split
const modules = new Map(); // mod -> {stmts:[], declared:Set}
const declOwner = new Map();
let currentMod = RANGES[0][1];
for (const stmt of ast.program.body) {
  const declared = Object.keys(t.getBindingIdentifiers(stmt, false, true));
  for (const n of declared) if (MARKERS.has(n)) { currentMod = MARKERS.get(n); break; }
  const mod = currentMod;
  if (!modules.has(mod)) modules.set(mod, { stmts: [], declared: new Set() });
  const m = modules.get(mod);
  m.stmts.push(stmt);
  const ids = t.getBindingIdentifiers(stmt, false, true);
  for (const n of Object.keys(ids)) { m.declared.add(n); declOwner.set(n, mod); }
}
// references per module
const refs = new Map();
for (const [mod, m] of modules) {
  const file = t.file(t.program(m.stmts.map((s) => t.cloneNode(s, true))));
  const used = new Set(), libs = new Set();
  let usesT = false;
  traverse(file, {
    "Identifier|JSXIdentifier"(p) {
      const n = p.node.name;
      if (p.isIdentifier() && p.parentPath.isMemberExpression({ property: p.node }) && !p.parent.computed) return;
      if (p.isIdentifier() && p.parentPath.isObjectProperty({ key: p.node }) && !p.parent.computed && !p.parent.shorthand) return;
      if (p.isJSXIdentifier() && (p.parentPath.isJSXAttribute() || p.parentPath.isJSXMemberExpression({ property: p.node }))) return;
      if (n === "msg" && !p.scope.hasBinding("msg")) usesT = true;
      if (p.scope.hasBinding(n)) return;
      if (declOwner.has(n) && declOwner.get(n) !== mod) used.add(n);
      libs.add(n);
    },
  }, undefined, {});
  refs.set(mod, { used, libs, usesT, file });
}
const exportsNeeded = new Map();
for (const [mod, r] of refs) for (const n of r.used) {
  const owner = declOwner.get(n);
  if (!exportsNeeded.has(owner)) exportsNeeded.set(owner, new Set());
  exportsNeeded.get(owner).add(n);
}
const relImport = (from, to) => "@/" + to;
let total = 0;
for (const [mod, m] of modules) {
  const r = refs.get(mod);
  const lines = [];
  const libImports = new Map();
  const add = (src, spec) => { if (!libImports.has(src)) libImports.set(src, new Set()); libImports.get(src).add(spec); };
  for (const n of r.libs) {
    if (n === "React") add("react", "* as React");
    else if (n.startsWith("Icon.")) add("lucide-react", "* as Icon");
    else if (n === "Icon") add("lucide-react", "* as Icon");
    else if (n === "z") add("zod", "{z}");
    else if (n === "Dialog" || n === "PopoverPrimitive" || n === "TabsPrimitive") add(Object.entries(NS_NAMES).find(([, v]) => v === n)[0], `* as ${n}`);
    else if (n === "ReactMarkdown") add("react-markdown", "default ReactMarkdown");
    else if (n === "remarkGfm") add("remark-gfm", "default remarkGfm");
    else if (n === "clsx") add("clsx", "{clsx}");
    else if (n === "ReactDOMClient") add("react-dom/client", "* as ReactDOMClient");
    else {
      const f = Object.values(FREE).find((x) => x[0] === n);
      if (f) add(f[1], `{${n}}`);
    }
  }
  if (r.usesT) add("@/i18n", "{msg}");
  for (const n of [...r.used].sort()) add(relImport(mod, declOwner.get(n)), `{${n}}`);
  for (const [src, specs] of libImports) {
    const named = [...specs].filter((s) => s.startsWith("{")).map((s) => s.slice(1, -1));
    const others = [...specs].filter((s) => !s.startsWith("{"));
    for (const o of others) {
      if (o.startsWith("* as")) lines.push(`import ${o} from "${src}";`);
      else if (o.startsWith("default ")) lines.push(`import ${o.slice(8)} from "${src}";`);
    }
    if (named.length) lines.push(`import { ${[...new Set(named)].join(", ")} } from "${src}";`);
  }
  const exp = exportsNeeded.get(mod) ?? new Set();
  const body = m.stmts.map((s) => {
    const code = generate(s, { jsescOption: { minimal: true } }).code;
    const ids = Object.keys(t.getBindingIdentifiers(s, false, true));
    return ids.some((n) => exp.has(n)) ? `export ${code}` : code;
  });
  const header = `// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).\n`;
  const ext = /<[A-Za-z>]/.test(body.join("\n")) ? ".jsx" : ".js";
  const file = path.join(OUT, mod + ext);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, header + lines.join("\n") + "\n\n" + body.join("\n\n") + "\n");
  total++;
}
fs.writeFileSync(path.join(OUT, "i18n/locales/en.extracted.json"), JSON.stringify(Object.fromEntries([...i18n].sort()), null, 2));
console.log("modules", total, "i18n strings", i18n.size);
