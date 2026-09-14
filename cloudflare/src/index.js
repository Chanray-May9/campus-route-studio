import {digest} from './crypto.js';
import {routeEntry} from './routes.js';
const json=(data,status=200)=>Response.json(data,{status});
class Problem extends Error{constructor(status,message){super(message);this.status=status;}}
const fail=(status,message)=>{throw new Problem(status,message);};
async function admin(request,env){if(!env.CR_ADMIN_TOKEN||env.CR_ADMIN_TOKEN.length<32)fail(503,'管理员配置尚未完成');const auth=request.headers.get('authorization')||'';if(!auth.startsWith('Bearer '))fail(401,'需要管理员会话');if(await digest(auth.slice(7))!==await digest(env.CR_ADMIN_TOKEN))fail(403,'管理员密码不正确');}
async function body(request){if(Number(request.headers.get('content-length')||0)>1500000)fail(413,'请求过大');const raw=await request.text();if(raw.length>1500000)fail(413,'请求过大');try{const data=JSON.parse(raw);if(!data||typeof data!=='object'||Array.isArray(data))throw Error();return data;}catch{fail(400,'JSON 格式不正确');}}
async function route(request,env){
 const url=new URL(request.url),path=url.pathname,method=request.method;
 if(path==='/health'&&method==='GET')return json({ok:true,storage:'D1',free:true,version:'0.3.0'});
 if(method==='GET'&&(path==='/'||path==='/admin'||path==='/admin.js')){const asset=new URL(url);asset.pathname=path==='/admin.js'?'/admin.js':'/admin.html';return env.ASSETS.fetch(new Request(asset));}
 if(!env.DB)fail(503,'轨迹数据库未配置');
 const db=env.DB.withSession('first-primary');
 const origin=request.headers.get('origin');if(method!=='GET'&&origin&&origin!==url.origin)fail(403,'请求来源不正确');
 if((path==='/api/routes'||path==='/api/admin/routes')&&method==='GET'){if(path==='/api/admin/routes')await admin(request,env);const list=await db.prepare('SELECT payload FROM remote_routes ORDER BY updated DESC').all();return json({entries:list.results.map(r=>JSON.parse(r.payload))});}
 if(path==='/api/admin/routes'&&method==='POST'){await admin(request,env);const entry=routeEntry(await body(request));const result=await db.prepare('INSERT INTO remote_routes SELECT ?,?,? WHERE (SELECT COUNT(*) FROM remote_routes)<50 OR EXISTS(SELECT 1 FROM remote_routes WHERE id=?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated=excluded.updated').bind(entry.id,JSON.stringify(entry),Date.now()/1000,entry.id).run();if(!result.meta.changes)fail(400,'最多发布 50 条轨迹');return json(entry);}
 if(path.startsWith('/api/admin/routes/')&&method==='DELETE'){await admin(request,env);await db.prepare('DELETE FROM remote_routes WHERE id=?').bind(decodeURIComponent(path.slice(18))).run();return json({deleted:true});}
 fail(404,'接口不存在');
}
export default{async fetch(request,env){let response;try{response=await route(request,env);}catch(e){response=json({detail:e instanceof Problem?e.message:'输入或轨迹格式不正确'},e instanceof Problem?e.status:400);}const headers=new Headers(response.headers);headers.set('Cache-Control','no-store');headers.set('Referrer-Policy','no-referrer');headers.set('X-Content-Type-Options','nosniff');headers.set('Content-Security-Policy',"default-src 'self';script-src 'self';style-src 'self' 'unsafe-inline';frame-ancestors 'none';base-uri 'none';object-src 'none';form-action 'self'");return new Response(response.body,{status:response.status,headers});}};
