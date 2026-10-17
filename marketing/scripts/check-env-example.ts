import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

type ObjectKind = "process" | "env";
export type EnvInventory = { names: string[]; errors: string[] };

const excludedDirectories = new Set(["node_modules", ".next", ".git", "__tests__", "e2e", "playwright-report", "test-results"]);

export function sourceFiles(root: string): string[] {
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const path = join(root, entry.name);
    if (entry.isDirectory()) return excludedDirectories.has(entry.name) ? [] : sourceFiles(path);
    return /\.(?:[cm]?[jt]sx?)$/.test(entry.name) && !/\.(?:test|spec)\.[^.]+$/.test(entry.name) && !entry.name.endsWith(".d.ts") ? [path] : [];
  });
}

function unwrap(node: ts.Node): ts.Node {
  while (ts.isParenthesizedExpression(node) || ts.isAsExpression(node) || ts.isTypeAssertionExpression(node) || ts.isNonNullExpression(node) || ts.isSatisfiesExpression(node)) node = node.expression;
  return node;
}

function staticKey(node: ts.Node | undefined): string | undefined {
  if (!node) return;
  if (ts.isComputedPropertyName(node)) return ts.isStringLiteral(node.expression) || ts.isNoSubstitutionTemplateLiteral(node.expression) ? node.expression.text : undefined;
  if (ts.isIdentifier(node) || ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
}

function memberKey(node: ts.PropertyAccessExpression | ts.ElementAccessExpression): string | undefined {
  if (ts.isPropertyAccessExpression(node)) return node.name.text;
  const key = node.argumentExpression;
  return key && (ts.isStringLiteral(key) || ts.isNoSubstitutionTemplateLiteral(key)) ? key.text : undefined;
}

export function inventoryEnvironment(files: string[]): EnvInventory {
  const program = ts.createProgram(files, { allowJs: true, moduleResolution: ts.ModuleResolutionKind.Bundler, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ESNext, jsx: ts.JsxEmit.Preserve, skipLibCheck: true });
  const checker = program.getTypeChecker();
  const roots = new Set(files.map((file) => resolve(file)));
  const sources = program.getSourceFiles().filter((file) => roots.has(resolve(file.fileName)));
  const objects = new Map<ts.Symbol, ObjectKind>();
  const names = new Set<string>();
  const errors = new Set<string>();
  let changed = false;

  function error(node: ts.Node, message: string) {
    const source = node.getSourceFile();
    const { line } = source.getLineAndCharacterOfPosition(node.getStart());
    errors.add(`${source.fileName}:${line + 1}: ${message}`);
  }

  function kind(node: ts.Node): ObjectKind | undefined {
    node = unwrap(node);
    if (ts.isIdentifier(node)) {
      let symbol = checker.getSymbolAtLocation(node);
      if (symbol && objects.has(symbol)) return objects.get(symbol);
      if (symbol && symbol.flags & ts.SymbolFlags.Alias) symbol = checker.getAliasedSymbol(symbol);
      if (symbol && objects.has(symbol)) return objects.get(symbol);
      if (node.text === "process" && !symbol?.declarations?.some((declaration) => roots.has(resolve(declaration.getSourceFile().fileName)))) return "process";
    }
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "require" && node.arguments.length === 1 && ts.isStringLiteral(node.arguments[0]) && ["process", "node:process"].includes(node.arguments[0].text)) return "process";
    if ((ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) && memberKey(node) === "process" && ts.isIdentifier(node.expression) && ["globalThis", "global"].includes(node.expression.text)) return "process";
    if ((ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) && kind(node.expression) === "process" && memberKey(node) === "env") return "env";
  }

  function bind(name: ts.BindingName, value: ObjectKind) {
    if (ts.isIdentifier(name)) {
      const symbol = checker.getSymbolAtLocation(name);
      if (symbol && objects.has(symbol) && objects.get(symbol) !== value) return error(name, "Unsupported mixed process/environment alias");
      if (symbol && !objects.has(symbol)) {
        objects.set(symbol, value);
        changed = true;
      }
      return;
    }
    if (!ts.isObjectBindingPattern(name)) return error(name, "Unsupported environment array binding");
    for (const entry of name.elements) {
      if (entry.dotDotDotToken) {
        error(entry, "Unsupported environment rest binding");
        continue;
      }
      const key = staticKey(entry.propertyName ?? entry.name);
      if (!key) error(entry, "Unsupported dynamic environment binding");
      else if (value === "env") names.add(key);
      else if (key === "env") bind(entry.name, "env");
    }
  }

  function callParameter(node: ts.CallExpression, index: number): ts.ParameterDeclaration | undefined {
    const declaration = checker.getResolvedSignature(node)?.declaration;
    if (!declaration || !roots.has(resolve(declaration.getSourceFile().fileName))) return;
    const parameter = declaration.parameters[index];
    return parameter && ts.isParameter(parameter) && !parameter.dotDotDotToken ? parameter : undefined;
  }

  function walk(node: ts.Node, visit: (node: ts.Node) => void) {
    visit(node);
    ts.forEachChild(node, (child) => walk(child, visit));
  }

  do {
    changed = false;
    for (const source of sources) walk(source, (node) => {
      if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier) && ["process", "node:process"].includes(node.moduleSpecifier.text)) {
        if (node.importClause?.name) bind(node.importClause.name, "process");
        const bindings = node.importClause?.namedBindings;
        if (bindings && ts.isNamespaceImport(bindings)) bind(bindings.name, "process");
        if (bindings && ts.isNamedImports(bindings)) for (const entry of bindings.elements) if ((entry.propertyName ?? entry.name).text === "env") bind(entry.name, "env");
      }
      if ((ts.isVariableDeclaration(node) || ts.isParameter(node)) && node.initializer) {
        const value = kind(node.initializer);
        if (value) bind(node.name, value);
      }
      if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken && ts.isIdentifier(node.left)) {
        const value = kind(node.right);
        if (value) bind(node.left, value);
      }
      if (ts.isCallExpression(node)) node.arguments.forEach((argument, index) => {
        const value = kind(argument);
        const parameter = callParameter(node, index);
        if (value && parameter) bind(parameter.name, value);
      });
    });
  } while (changed);

  for (const source of sources) walk(source, (node) => {
    if (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) {
      const owner = kind(node.expression);
      const key = memberKey(node);
      if (owner && !key) error(node, "Unsupported dynamic environment access");
      if (owner === "env" && key) names.add(key);
    }
    const value = kind(node);
    if (!value) return;
    const parent = node.parent;
    if (!parent) return;
    if (ts.isIdentifier(node) && (
      ((ts.isVariableDeclaration(parent) || ts.isParameter(parent) || ts.isBindingElement(parent) || ts.isImportSpecifier(parent) || ts.isImportClause(parent) || ts.isNamespaceImport(parent)) && parent.name === node)
      || (ts.isImportSpecifier(parent) && parent.propertyName === node)
      || (ts.isPropertyAccessExpression(parent) && parent.name === node)
      || (ts.isBinaryExpression(parent) && parent.left === node)
    )) return;
    if ((ts.isPropertyAccessExpression(parent) || ts.isElementAccessExpression(parent)) && parent.expression === node) return;
    if (ts.isParenthesizedExpression(parent) || ts.isAsExpression(parent) || ts.isTypeAssertionExpression(parent) || ts.isNonNullExpression(parent) || ts.isSatisfiesExpression(parent)) return;
    if ((ts.isVariableDeclaration(parent) || ts.isParameter(parent)) && parent.initializer === node) return;
    if (ts.isBinaryExpression(parent) && parent.right === node && parent.operatorToken.kind === ts.SyntaxKind.EqualsToken && ts.isIdentifier(parent.left)) return;
    if (ts.isCallExpression(parent)) {
      const parameter = callParameter(parent, parent.arguments.indexOf(node as ts.Expression));
      if (parameter) return;
    }
    error(node, `Unsupported ${value} object use; use static keys and a local wrapper parameter`);
  });
  return { names: [...names].sort(), errors: [...errors].sort() };
}

export function checkExample(root: string): EnvInventory {
  const inventory = inventoryEnvironment(sourceFiles(root));
  const example = readFileSync(join(root, ".env.example"), "utf8");
  const declared = new Set([...example.matchAll(/^([A-Z][A-Z0-9_]*)=/gm)].map((match) => match[1]));
  for (const name of inventory.names) if (!declared.has(name)) inventory.errors.push(`.env.example is missing ${name}`);
  return inventory;
}

if (resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url)) {
  const root = resolve(process.argv[2] ?? join(dirname(fileURLToPath(import.meta.url)), ".."));
  const result = checkExample(root);
  if (result.errors.length) {
    for (const message of result.errors) console.error(message.replaceAll(`${root}/`, ""));
    process.exitCode = 1;
  } else console.log(`Environment example covers ${result.names.length} static names.`);
}
