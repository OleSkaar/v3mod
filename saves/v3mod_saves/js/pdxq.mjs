// usage: node pdxq.mjs SAVE /path/to/key [/another ...]  -> JSON on stdout (object keyed by path)
import { readFileSync } from "node:fs";
import { Jomini } from "jomini";
const [file, ...paths] = process.argv.slice(2);
const buf = readFileSync(file);
const t0 = Date.now();
const parser = await Jomini.initialize();
const out = parser.parseText(buf, { encoding: "utf8" }, (q) => {
  const r = {};
  for (const p of paths) r[p] = q.at(p);
  return r;
});
process.stderr.write(`parsed ${(buf.length/1e6).toFixed(0)} MB in ${Date.now()-t0} ms\n`);
process.stdout.write(JSON.stringify(out));
