const fs = require('node:fs'); const path = require('node:path'); const { validateBaseUrl } = require('../utils/api');
const args=process.argv.slice(2); const get=name=>{const i=args.indexOf(name);return i<0?'':args[i+1];}; const root=path.resolve(__dirname,'..');
const appid=get('--appid'); const base=get('--api');
if (!/^wx[a-zA-Z0-9]{16}$/.test(appid)) throw new Error('提供微信平台实际分配的测试/开发 AppID：--appid wx...；不生成假 AppID');
const endpoint=validateBaseUrl(base,false);
const config=JSON.parse(fs.readFileSync(path.join(root,'project.config.json'))); config.appid=appid;
fs.writeFileSync(path.join(root,'project.private.config.json'),JSON.stringify({appid,projectname:config.projectname,setting:config.setting},null,2)+'\n');
// The normal project config must carry the real AppID for supported CLI imports.
// AppID is public configuration; AppSecret/password/API keys are never accepted.
config.appid=appid;fs.writeFileSync(path.join(root,'project.config.json'),JSON.stringify(config,null,2)+'\n');
fs.writeFileSync(path.join(root,'environment.js'),'// Public endpoint configuration only; never add credentials.\nmodule.exports = '+JSON.stringify({apiBaseUrl:endpoint,allowSimulatorHttp:false,pollIntervalMs:15000})+';\n');
console.log('已设置实际 AppID 与 HTTPS 地址，域名和账号能力仍由微信平台与开发者工具核验。');
