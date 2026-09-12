// Start `next dev`, working around Node 25+'s server-side localStorage.
//
// Node 25 defines a `localStorage` global on the server whose methods are
// undefined. Next's own dev overlay reads it while server-rendering, so on
// Node 25 every page returned 500 ("localStorage.getItem is not a function").
// Disabling the experimental Web Storage API restores Node 20–24 behaviour.
// The flag is unknown to Node 20 (which CI uses), so add it only when needed.
import { spawn } from "node:child_process"

const major = Number(process.versions.node.split(".")[0])
const env = { ...process.env }
if (major >= 25 && !(env.NODE_OPTIONS ?? "").includes("webstorage")) {
  env.NODE_OPTIONS = `${env.NODE_OPTIONS ?? ""} --no-experimental-webstorage`.trim()
}

const child = spawn("next", ["dev", ...process.argv.slice(2)], {
  stdio: "inherit",
  env,
  shell: true, // resolves next(.cmd) from node_modules/.bin on every platform
})
child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)))
