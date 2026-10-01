const fs=require('node:fs');const path=require('node:path');const os=require('node:os');const {execFileSync}=require('node:child_process');
const candidates=['/Applications/wechatwebdevtools.app/Contents/MacOS/cli','/Applications/微信开发者工具.app/Contents/MacOS/cli',path.join(os.homedir(),'Applications/wechatwebdevtools.app/Contents/MacOS/cli')];
const tool=candidates.find(candidate=>fs.existsSync(candidate));
const result={checked_at:new Date().toISOString(),platform:process.platform,cli:tool||null,developer_tools_installed:Boolean(tool),native_compile_verified:false,device_preview_verified:false,capabilities_verified:[],note:'无实际测试/开发账号及可达 HTTPS 配置时，不声称已预览。'};
if(tool){try{result.help_excerpt=execFileSync(tool,['--help'],{timeout:10000,encoding:'utf8'}).slice(0,4000);}catch(error){result.cli_error=String(error.message);}}
console.log(JSON.stringify(result,null,2));
