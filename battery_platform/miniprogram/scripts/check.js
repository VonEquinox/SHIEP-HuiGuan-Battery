const fs = require('node:fs'); const path = require('node:path'); const vm = require('node:vm'); const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..'); const app = JSON.parse(fs.readFileSync(path.join(root,'app.json')));
let handlers = 0;
for (const page of app.pages) {
  for (const extension of ['.js','.json','.wxml']) if (!fs.existsSync(path.join(root,page+extension))) throw new Error('missing page '+page+extension);
  JSON.parse(fs.readFileSync(path.join(root,page+'.json')));
  const script = fs.readFileSync(path.join(root,page+'.js'),'utf8'); let definition;
  vm.runInNewContext(script,{Page:value=>{definition=value;},require:value=>require(path.resolve(root,path.dirname(page),value)),Date,Number,setInterval,clearInterval,console},{filename:page+'.js'});
  const markup = fs.readFileSync(path.join(root,page+'.wxml'),'utf8');
  for (const match of markup.matchAll(/bind(?:tap|input|change)="([a-zA-Z_$][\w$]*)"/g)) { if (typeof definition[match[1]] !== 'function') throw new Error(page+': missing event '+match[1]); handlers++; }
}
function visit(folder) { for (const entry of fs.readdirSync(folder,{withFileTypes:true})) { const file=path.join(folder,entry.name); if(entry.isDirectory()) visit(file); else if(entry.name.endsWith('.js')) execFileSync(process.execPath,['--check',file]); else if(entry.name.endsWith('.json')) JSON.parse(fs.readFileSync(file)); } }
visit(root);
// XML syntax check is useful for escaped template expressions, but does not
// claim to substitute for the actual WeChat WXML compiler or device runtime.
const program = "from pathlib import Path\nimport xml.etree.ElementTree as E\nimport sys\nfor p in Path(sys.argv[1]).rglob('*.wxml'):\n E.fromstring('<root xmlns:wx=\"urn:wechat\">'+p.read_text()+'</root>')\nprint('WXML XML structure passed')";
execFileSync('python3',['-c',program,root],{stdio:'inherit'});
console.log(JSON.stringify({pages:app.pages.length,eventBindings:handlers,syntax:'passed',nativeCompiler:'not_run'}));
