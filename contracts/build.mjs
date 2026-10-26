// Canonical contract source. Run: node contracts/build.mjs
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const check=process.argv.includes('--check');
function output(p,body){const dest=path.join(root,p);if(check){if(!fs.existsSync(dest)||fs.readFileSync(dest,'utf8').replace(/\r\n/g,'\n')!==body)throw new Error(`Generated artifact drift: ${p}. Run node contracts/build.mjs`);return;}fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,body);}
function write(p,x){output(p,JSON.stringify(x,null,2)+'\n');}
const s=(extra={})=>({type:'string',...extra});
const n=(min=0)=>({type:'integer',minimum:min});
const bool={type:'boolean'};
const en=(...values)=>({type:'string',enum:values});
const ref=name=>({$ref:`#/$defs/${name}`});
const arr=items=>({type:'array',items});
const nullable=x=>({anyOf:[x,{type:'null'}]});
const obj=(properties,required=Object.keys(properties))=>({type:'object',properties,required,additionalProperties:false});
const id=s({format:'uuid'}), date=s({format:'date-time',pattern:'Z$'}), text=s({minLength:1}), version=s({pattern:'^[0-9]+\\.[0-9]+\\.[0-9]+(?:-[a-z0-9.-]+)?$'});
const key=s({pattern:'^(?!/)(?!.*\\.\\.)(?!.*\\\\)[a-zA-Z0-9_./-]+$'});
const D={};
D.RoomMap=en('standard','hexagon','circular');
D.RoomMove=obj({from:s({minLength:2,maxLength:8}),to:s({minLength:2,maxLength:8})});
D.RoomCreate=obj({map:ref('RoomMap')});
D.RoomJoin=obj({code:s({pattern:'^[A-Z2-9]{8}$'})});
D.RoomCommand=obj({revision:n(),action:en('ready','unready','move','resign','rematch','leave'),move:ref('RoomMove')},['revision','action']);
D.Room=obj({id,code:s({pattern:'^[A-Z2-9]{8}$'}),map:ref('RoomMap'),revision:n(),round:n(1),status:en('waiting','playing','finished','closed'),players:arr(obj({id,side:en('BLUE','RED'),ready:bool,rematch:bool})),fen:nullable(s()),position:{type:'object',additionalProperties:en('B','P','K','b','p','k')},turn:nullable(en('BLUE','RED')),moves:arr(ref('RoomMove')),legal_moves:arr(ref('RoomMove')),result:nullable(obj({winner:en('BLUE','RED'),reason:en('GOAL','WIPEOUT','STALEMATE','MOVE_LIMIT','RESIGNED')}))});
D.RoomList=arr(ref('Room'));
D.ProfileEdit=obj({display_name:s({minLength:1,maxLength:40,pattern:'\\S'}),bio:s({maxLength:240}),avatar:en('hammer','paper','scissors','fox','owl','cat'),frame:en('none','bronze','laurel','double'),color:en('amber','jade','ocean','violet','rose')});
D.ProfileStats=obj({played:n(),wins:n(),losses:n(),by_map:arr(obj({map:ref('RoomMap'),played:n(),wins:n(),losses:n()}))});
D.Profile=obj({user_id:id,...D.ProfileEdit.properties,stats:ref('ProfileStats')});
D.Side=en('BLUE','RED'); D.Language=en('python','cpp','java','node');
D.Reason=en('GOAL','WIPEOUT','STALEMATE','TIMEOUT','ILLEGAL_MOVE','CRASH','MOVE_LIMIT');
D.SubmissionStatus=en('queued','building','ready','failed');
D.GameStatus=en('queued','running','finished','infra_error');
D.MatchStatus=en('queued','running','finished','blocked');
D.RoundStatus=en('draft','frozen','running','finished');
D.TournamentStatus=en('draft','drawn','running','finished');
D.Error=obj({error:obj({code:text,message:text,details:{type:'object',additionalProperties:true}}),request_id:id});
D.WorkerError=obj({code:text,message:text});
D.User=obj({id,email:s({format:'email'}),role:en('member','captain','admin'),team_id:nullable(id),is_active:bool});
D.Auth=obj({access_token:text,token_type:{const:'bearer'},expires_in:{const:900},user:ref('User')});
D.Login=obj({email:s({format:'email'}),password:s({minLength:1,maxLength:256})});
D.Register=obj({email:s({format:'email',maxLength:320}),password:s({minLength:8,maxLength:256}),team_name:s({minLength:1,maxLength:100,pattern:'\\S'})});
D.ActiveBot=obj({team_id:id,scope:en('scrimmage','tournament'),submission_id:id});
D.SetActiveBot=obj({scope:en('scrimmage','tournament'),submission_id:id});
D.Team=obj({id,name:s({minLength:1,maxLength:100}),slug:s({pattern:'^[a-z0-9]+(?:-[a-z0-9]+)*$'}),status:en('pending','approved','disqualified'),is_locked:bool,seed:nullable(n(1)),group_id:nullable(id),members:arr(ref('User')),active_bots:arr(ref('ActiveBot'))});
D.TeamPatch=obj({name:s({minLength:1,maxLength:100})});
D.AdminTeamPatch=obj({name:s({minLength:1,maxLength:100}),status:en('pending','approved','disqualified'),is_locked:bool,seed:nullable(n(1)),reason:text},['reason']); D.AdminTeamPatch.minProperties=2;
D.TeamCreate=obj({name:text,slug:s({pattern:'^[a-z0-9]+(?:-[a-z0-9]+)*$'}),captain_email:s({format:'email'}),seed:nullable(n(1))});
D.TeamPublic=obj({id,name:text,slug:text});
D.Submission=obj({id,team_id:id,language:ref('Language'),status:ref('SubmissionStatus'),sha256:s({pattern:'^[a-f0-9]{64}$'}),submitted_at:date,build_error:nullable(ref('WorkerError'))});
D.SubmissionAccepted=obj({id,status:{const:'queued'}});
D.BuildLog=obj({submission_id:id,status:ref('SubmissionStatus'),text:s(),truncated:bool,updated_at:date});
D.ScrimmageCreate=obj({opponent_team_id:id});
D.MatchAccepted=obj({match_id:id,status:{const:'queued'}});
D.ScrimmagePauseReason=en('queue_paused','tournament_load','scrimmage_backlog');
D.ScrimmageAdmission=obj({accepting:bool,paused_reason:nullable(ref('ScrimmagePauseReason'))});
D.ScrimmageAdmission.allOf=[{if:{properties:{accepting:{const:true}}},then:{properties:{paused_reason:{type:'null'}}},else:{properties:{paused_reason:ref('ScrimmagePauseReason')}}}];
D.Quota=obj({limit:{const:60},used:n(),remaining:n(),resets_at:date,active:n(),active_limit:n(1),admission:ref('ScrimmageAdmission')});
D.SignedUrl=obj({url:s({format:'uri'}),expires_at:date});
D.Result=obj({winner:ref('Side'),reason:ref('Reason'),plies:n()});
D.Game=obj({id,match_id:id,game_index:n(1),attempt:n(1),is_current:bool,blue_submission_id:id,red_submission_id:id,map_id:{const:'standard'},engine_version:version,ruleset_id:{const:'dev-v1'},status:ref('GameStatus'),result:nullable(ref('Result')),duration_ms:nullable(n()),replay_available:bool});
D.Game.allOf=[{if:{properties:{status:{const:'finished'}}},then:{properties:{result:ref('Result'),duration_ms:n(),replay_available:{const:true}}},else:{properties:{result:{type:'null'},replay_available:{const:false}}}}];
D.Match=obj({id,tournament_id:nullable(id),round_id:nullable(id),stage:en('scrimmage','group','quarterfinal','semifinal','third_place','final'),team_a:ref('TeamPublic'),team_b:ref('TeamPublic'),best_of:en('two_games','first_to_2','first_to_3'),status:ref('MatchStatus'),winner_team_id:nullable(id),score_a:n(),score_b:n(),games:arr(ref('Game'))});
D.Announcement=obj({id,title:text,body:s(),published_at:nullable(date)});
D.AnnouncementWrite=obj({title:s({minLength:1,maxLength:200}),body:s({maxLength:50000})});
D.ReasonBody=obj({reason:s({minLength:1,maxLength:2000})});
D.Tournament=obj({id,name:text,status:ref('TournamentStatus'),engine_version:version,ruleset_id:{const:'dev-v1'},draw_seed:nullable(n()),draw_locked:bool});
D.TournamentCreate=obj({name:text,engine_version:version,ruleset_id:{const:'dev-v1'}});
D.DrawRequest=obj({reason:text});
D.Draw=obj({tournament_id:id,draw_seed:n(),locked:bool,groups:arr(obj({id,label:en('A','B','C','D'),team_ids:arr(id)}))});
D.Round=obj({id,tournament_id:id,stage:en('group','quarterfinal','semifinal','third_place','final'),status:ref('RoundStatus'),freeze_at:nullable(date),snapshot_id:nullable(id),matches_total:n(),matches_finished:n()});
D.RoundCreate=obj({stage:en('group','quarterfinal','semifinal','third_place','final'),freeze_at:nullable(date)});
D.RoundPatch=obj({freeze_at:nullable(date),reason:text});
D.FrozenBot=obj({team_id:id,submission_id:id});
D.Snapshot=obj({id,round_id:id,frozen_at:date,bots:arr(ref('FrozenBot'))});
D.RunAccepted=obj({round_id:id,status:{const:'running'},match_ids:arr(id)});
D.RerunAccepted=obj({game_id:id,previous_game_id:id,attempt:n(2),status:{const:'queued'}});
D.Override=obj({winner_team_id:nullable(id),score_a:n(),score_b:n(),reason:text});
D.Standing=obj({group_id:id,team:ref('TeamPublic'),rank:n(1),played:n(),won:n(),drawn:n(),lost:n(),points:n(),game_diff:{type:'integer'},games_won:n(),winning_plies:n()});
D.BracketSlot=obj({round:en('quarterfinal','semifinal','third_place','final'),slot_index:n(1),source_rule:text,team:nullable(ref('TeamPublic')),match_id:nullable(id)});
D.Worker=obj({id:text,kind:en('build','match'),last_seen_at:date,status:en('idle','busy','offline'),job_id:nullable(id)});
D.Queue=obj({queues:arr(obj({name:en('build','match:tournament','match:scrimmage'),paused:bool,queued:n(),running:n(),failed:n()})),workers:arr(ref('Worker')),scrimmage_admission:ref('ScrimmageAdmission')});
D.QueueControl=obj({name:en('build','match:tournament','match:scrimmage'),paused:bool,reason:text});
D.SourceTree=obj({submission_id:id,files:arr(obj({path:key,size_bytes:n(),language:s()}))});
D.SourceFile=obj({submission_id:id,path:key,content:s(),truncated:bool});
D.GameLogs=obj({game_id:id,BLUE:s(),RED:s(),blue_truncated:bool,red_truncated:bool});
D.Similarity=obj({submission_a:id,submission_b:id,score:{type:'number',minimum:0,maximum:1},checked_at:date});
D.Audit=obj({id,actor_user_id:nullable(id),action:text,target_type:text,target_id:nullable(id),payload:{type:'object',additionalProperties:true},created_at:date});
D.ImportRequest=obj({csv:s({minLength:1,maxLength:1048576})});
D.ImportResult=obj({created:arr(ref('TeamPublic')),errors:arr(obj({row:n(1),code:text,message:text}))});
D.Capabilities=obj({contract_version:{const:'1.3.0'},languages:arr(ref('Language')),max_upload_bytes:{const:1048576},max_files:{const:50},ruleset_id:{const:'dev-v1'},ruleset_status:{const:'development'},tournament_enabled:bool});
D.Docs=obj({rules_markdown:s(),protocol_markdown:s(),starter_kits:arr(obj({language:ref('Language'),engine_version:version,url:s({format:'uri'}),sha256:s({pattern:'^[a-f0-9]{64}$'})}))});
D.Health=obj({status:en('ok','degraded'),contract_version:{const:'1.3.0'}});
D.Ack=obj({accepted:{const:true}});
const player=obj({team:s({pattern:'^[a-z0-9]+(?:-[a-z0-9]+)*$'}),submission_id:id});
D.Players=obj({BLUE:player,RED:player});
D.GameConfig=obj({engine_version:version,ruleset_id:{const:'dev-v1'},map_id:{const:'standard'},initial_fen:s({pattern:'^[BPKbpk1-9]+(?:/[BPKbpk1-9]+){8}$'}),players:ref('Players'),budget_ms:{const:60000},init_ms:{const:10000},grace_ms:{const:50},hard_timeout_extra_ms:{const:1000},max_turns:{const:300},seed:n()});
D.BuildJob=obj({schema_version:{const:1},job_id:id,submission_id:id,language:ref('Language'),source_key:key,source_sha256:s({pattern:'^[a-f0-9]{64}$'}),engine_version:version});
D.MatchJob=obj({schema_version:{const:1},job_id:id,game_id:id,attempt:n(1),blue_image:text,red_image:text,map_id:{const:'standard'},engine_version:version,players:ref('Players'),config:ref('GameConfig')});
const buildBase={schema_version:{const:1},job_id:id,submission_id:id};
D.BuildResult={oneOf:[
 obj({...buildBase,status:{const:'building'},image_tag:{type:'null'},build_log_key:nullable(key),error:{type:'null'}}),
 obj({...buildBase,status:{const:'ready'},image_tag:text,build_log_key:key,error:{type:'null'}}),
 obj({...buildBase,status:{const:'failed'},image_tag:{type:'null'},build_log_key:nullable(key),error:ref('WorkerError')})]};
const gameBase={schema_version:{const:1},job_id:id,game_id:id,attempt:n(1)};
D.GameResultCallback={oneOf:[
 obj({...gameBase,status:{const:'running'},result:{type:'null'},replay_key:{type:'null'},log_key:{type:'null'},duration_ms:{const:0},error:{type:'null'}}),
 obj({...gameBase,status:{const:'finished'},result:ref('Result'),replay_key:key,log_key:key,duration_ms:n(),error:{type:'null'}}),
 obj({...gameBase,status:{const:'infra_error'},result:{type:'null'},replay_key:nullable(key),log_key:nullable(key),duration_ms:n(),error:obj({code:{const:'INFRA_ERROR'},message:text})})]};
const replayPlayer=obj({...player.properties,bot_name:s({maxLength:64})});
D.Replay=obj({format:{const:1},engine_version:version,ruleset_id:{const:'dev-v1'},map_id:{const:'standard'},initial_fen:D.GameConfig.properties.initial_fen,players:obj({BLUE:replayPlayer,RED:replayPlayer}),moves:arr(obj({ply:n(1),side:ref('Side'),move:s({pattern:'^[a-i][1-9][a-i][1-9]$'}),think_ms:n(),clock_ms:n(),capture:nullable(en('B','P','K','b','p','k')),debug:arr(s({pattern:'^#',maxLength:4096}))})),result:ref('Result')});
D.EngineResult=obj({winner:ref('Side'),reason:ref('Reason'),plies:n(),duration_ms:n(),replay:ref('Replay')});
const teamChannel=s({pattern:'^team:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'});
const channel={anyOf:[{const:'public'},teamChannel]};
D.WsClient={oneOf:[obj({type:{const:'auth'},access_token:text}),obj({type:{const:'subscribe'},channel}),obj({type:{const:'unsubscribe'},channel}),obj({type:{const:'ping'}})]};
const event=(type,data,privateOnly=false)=>obj({schema_version:{const:1},event_id:id,type:{const:type},channel:privateOnly?teamChannel:channel,occurred_at:date,data});
D.WsEvent={oneOf:[event('build.updated',obj({submission_id:id,status:ref('SubmissionStatus')}),true),event('game.finished',obj({game_id:id,match_id:id})),event('match.finished',obj({match_id:id})),event('standings.updated',obj({tournament_id:id,group_id:id})),event('announcement.published',obj({announcement_id:id}))]};
D.WsServer={oneOf:[ref('WsEvent'),obj({type:{const:'auth.ok'}}),obj({type:{const:'subscribed'},channel}),obj({type:{const:'unsubscribed'},channel}),obj({type:{const:'pong'}}),obj({type:{const:'error'},code:en('UNAUTHORIZED','FORBIDDEN','INVALID_MESSAGE','RATE_LIMITED','TOKEN_EXPIRED'),message:text})]};
D.WorkerHeartbeat=obj({worker_id:text,kind:en('build','match'),job_id:nullable(id),sent_at:date});
// Every list is a documented pagination object, including admin lists.
for(const name of ['Submission','Match','TeamPublic','Team','Tournament','Round','Standing','BracketSlot','Announcement','Similarity','Audit'])D[name+'Page']=obj({items:arr(ref(name)),page:n(1),page_size:{...n(1),maximum:100},total:n()});
const wrappers={'build-job':'BuildJob','match-job':'MatchJob','build-result':'BuildResult','game-result':'GameResultCallback','game-config':'GameConfig','engine-result':'EngineResult','replay':'Replay','websocket-client':'WsClient','websocket-event':'WsEvent','websocket-server':'WsServer','worker-heartbeat':'WorkerHeartbeat'};
for(const [file,name] of Object.entries(wrappers))write(`schemas/${file}.schema.json`,{$schema:'https://json-schema.org/draft/2020-12/schema',$ref:`common.schema.json#/$defs/${name}`});
const apiRef=name=>({$ref:`#/components/schemas/${name}`});
function apiConvert(x){if(Array.isArray(x))return x.map(apiConvert);if(x&&typeof x==='object')return Object.fromEntries(Object.entries(x).map(([k,v])=>[k,k==='$ref'?v.replace('#/$defs/','#/components/schemas/'):apiConvert(v)]));return x;}
const api={openapi:'3.1.0',info:{title:'OTTv2 Arena Contract',version:'1.3.0',description:'Development integration baseline; dev-v1 rules are provisional. JSON encoding is valid YAML 1.2. Generated from contracts/build.mjs.'},servers:[{url:'/api/v1'}],security:[{bearerAuth:[]}],paths:{},components:{securitySchemes:{bearerAuth:{type:'http',scheme:'bearer',bearerFormat:'JWT'},workerAuth:{type:'http',scheme:'bearer',description:'Worker credential, never a user JWT'},refreshCookie:{type:'apiKey',in:'cookie',name:'ottv2_refresh'}},schemas:apiConvert(D)}};
const operations=[];
function op(method,p,operationId,response,{request=null,status=200,role='member',list=false,query={},description='',multipart=false}={}){
 const parameters=[];
 for(const name of [...p.matchAll(/\{([^}]+)\}/g)].map(m=>m[1]))parameters.push({name,in:'path',required:true,schema:id});
 if(list) Object.assign(query,{page:{...n(1),default:1},page_size:{...n(1),maximum:100,default:20}});
 for(const [name,schema] of Object.entries(query))parameters.push({name,in:'query',required:['tournament_id','path'].includes(name),schema});
 const mutation=!['get','head'].includes(method)&&!['register','login','refresh','logout','buildCallback','gameCallback','workerHeartbeat'].includes(operationId);
 if(mutation)parameters.push({name:'Idempotency-Key',in:'header',required:true,schema:id,description:'Scoped by actor + method + path; retained 24h. Same key/body returns original status/body, different body returns 409.'});
 const o={operationId,summary:operationId,'x-role':role,description:description||`${role} access. ${list?'Stable ordering: created_at descending (or id if no timestamp), then id ascending. ':''}See contracts/behavior.md for authorization and state transitions.`,parameters,responses:{}};
 if(role==='public')o.security=[];
 if(role==='worker')o.security=[{workerAuth:[]}];
 if(role==='refresh')o.security=[{refreshCookie:[]}];
 if(['buildCallback','gameCallback'].includes(operationId))parameters.push({name:'X-Worker-Lease',in:'header',required:true,schema:id,description:'Current Redis lease owner token; backend verifies it before accepting callback.'});
 if(request)o.requestBody={required:true,content:{[multipart?'multipart/form-data':'application/json']:{schema:apiRef(request)}}};
 o.responses[status]={description:status===204?'No content':'Success',...(response?{content:{'application/json':{schema:apiRef(response)}}}:{})};
 for(const code of [400,401,403,404,409,413,422,429,500,503])o.responses[code]={description:'Error; see error.code',content:{'application/json':{schema:apiRef('Error')}}};
 api.paths[p]??={};api.paths[p][method]=o;operations.push({method,path:p,operationId,request,response,status,role,multipart});
}
op('get','/health','health','Health',{role:'public'});
op('get','/profiles/me','myProfile','Profile');
op('put','/profiles/me','updateMyProfile','Profile',{request:'ProfileEdit'});
op('get','/profiles/{user_id}','publicProfile','Profile',{role:'public'});
op('post','/rooms','createRoom','Room',{request:'RoomCreate',status:201});
op('get','/rooms','listRooms','RoomList');
op('post','/rooms/join','joinRoom','Room',{request:'RoomJoin'});
op('get','/rooms/{room_id}','getRoom','Room');
op('post','/rooms/{room_id}/commands','roomCommand','Room',{request:'RoomCommand'});
op('get','/capabilities','capabilities','Capabilities',{role:'public'});
op('post','/auth/login','login','Auth',{request:'Login',role:'public'});
op('post','/auth/register','register','Auth',{request:'Register',role:'public',status:201});
op('post','/auth/refresh','refresh','Auth',{role:'refresh'});
op('post','/auth/logout','logout',null,{status:204,role:'refresh'});
op('get','/auth/me','currentUser','User');
op('get','/teams/me','myTeam','Team'); op('patch','/teams/me','updateMyTeam','Team',{request:'TeamPatch',role:'captain'});
op('put','/teams/me/active-bot','setActiveBot','ActiveBot',{request:'SetActiveBot',role:'captain'});
op('get','/teams/opponents','listOpponents','TeamPublicPage',{list:true});
D.Upload=obj({file:s({format:'binary'}),language:ref('Language')});api.components.schemas.Upload=apiConvert(D.Upload);
op('post','/submissions','createSubmission','SubmissionAccepted',{request:'Upload',status:202,multipart:true});
op('get','/submissions','listSubmissions','SubmissionPage',{list:true,query:{status:ref('SubmissionStatus')}});
op('get','/submissions/{id}','getSubmission','Submission');
op('get','/submissions/{id}/build-log','getBuildLog','BuildLog');
op('get','/submissions/{id}/source','getOwnSource','SourceTree');
op('get','/submissions/{id}/source-file','getOwnSourceFile','SourceFile',{query:{path:key}});
op('post','/scrimmages','createScrimmage','MatchAccepted',{request:'ScrimmageCreate',status:202});
op('get','/scrimmages','listScrimmages','MatchPage',{list:true});op('get','/scrimmages/quota','scrimmageQuota','Quota');
op('get','/matches','listMatches','MatchPage',{list:true,query:{tournament_id:id,status:ref('MatchStatus')}});
op('get','/matches/{id}','getMatch','Match');op('get','/games/{id}','getGame','Game');
op('get','/games/{id}/replay','getReplayUrl','SignedUrl');
op('get','/standings','getStandings','StandingPage',{role:'public',list:true,query:{tournament_id:id,group_id:id}});
op('get','/bracket','getBracket','BracketSlotPage',{role:'public',list:true,query:{tournament_id:id}});
op('get','/tournaments','listTournaments','TournamentPage',{role:'public',list:true});
op('get','/tournaments/{id}','getTournament','Tournament',{role:'public'});
op('get','/tournaments/{id}/rounds','listRounds','RoundPage',{role:'public',list:true});
op('get','/announcements','listAnnouncements','AnnouncementPage',{role:'public',list:true});
op('get','/docs','getDocs','Docs',{role:'public'});
const admin=(method,p,operationId,response,options={})=>op(method,p,operationId,response,{...options,role:'admin'});
admin('get','/admin/teams','adminListTeams','TeamPage',{list:true});
admin('post','/admin/teams','adminCreateTeam','Team',{request:'TeamCreate',status:201});
admin('patch','/admin/teams/{id}','adminUpdateTeam','Team',{request:'AdminTeamPatch'});
admin('post','/admin/teams/import','adminImportTeams','ImportResult',{request:'ImportRequest',status:201});
admin('get','/admin/submissions','adminListSubmissions','SubmissionPage',{list:true,query:{team_id:id,language:ref('Language'),status:ref('SubmissionStatus')}});
admin('get','/admin/submissions/{id}','adminGetSubmission','Submission');
admin('get','/admin/submissions/{id}/source','adminGetSource','SourceTree');
admin('get','/admin/submissions/{id}/source-file','adminGetSourceFile','SourceFile',{query:{path:key}});
admin('get','/admin/submissions/{id}/build-log','adminBuildLog','BuildLog');
admin('get','/admin/tournaments','adminListTournaments','TournamentPage',{list:true});
admin('post','/admin/tournaments','adminCreateTournament','Tournament',{request:'TournamentCreate',status:201});
admin('get','/admin/tournaments/{id}/draw','adminGetDraw','Draw');
admin('post','/admin/tournaments/{id}/draw','adminDraw','Draw',{request:'DrawRequest'});
admin('post','/admin/tournaments/{id}/draw/lock','adminLockDraw','Draw',{request:'ReasonBody'});
admin('post','/admin/tournaments/{id}/rounds','adminCreateRound','Round',{request:'RoundCreate',status:201});
admin('get','/admin/tournaments/{id}/rounds','adminListRounds','RoundPage',{list:true});
admin('patch','/admin/rounds/{id}','adminUpdateRound','Round',{request:'RoundPatch'});
admin('post','/admin/rounds/{id}/freeze','adminFreezeRound','Snapshot',{request:'ReasonBody'});
admin('get','/admin/rounds/{id}/snapshot','adminGetSnapshot','Snapshot');
admin('post','/admin/rounds/{id}/run','adminRunRound','RunAccepted',{request:'ReasonBody',status:202});
admin('get','/admin/matches','adminListMatches','MatchPage',{list:true,query:{round_id:id,status:ref('MatchStatus')}});
admin('get','/admin/games/{id}/logs','adminGameLogs','GameLogs');
admin('post','/admin/games/{id}/rerun','adminRerunGame','RerunAccepted',{request:'ReasonBody',status:202});
admin('post','/admin/matches/{id}/override','adminOverrideMatch','Match',{request:'Override'});
admin('get','/admin/queue','adminQueue','Queue');admin('put','/admin/queue','adminControlQueue','Queue',{request:'QueueControl'});
admin('get','/admin/similarity','adminSimilarity','SimilarityPage',{list:true});
admin('get','/admin/audit-log','adminAuditLog','AuditPage',{list:true,query:{actor_user_id:id,action:text}});
admin('get','/admin/announcements','adminAnnouncements','AnnouncementPage',{list:true});
admin('post','/admin/announcements','adminCreateAnnouncement','Announcement',{request:'AnnouncementWrite',status:201});
admin('patch','/admin/announcements/{id}','adminUpdateAnnouncement','Announcement',{request:'AnnouncementWrite'});
admin('post','/admin/announcements/{id}/publish','adminPublishAnnouncement','Announcement',{request:'ReasonBody'});
op('post','/internal/builds/{id}','buildCallback','Ack',{request:'BuildResult',role:'worker'});
op('post','/internal/games/{id}','gameCallback','Ack',{request:'GameResultCallback',role:'worker'});
op('post','/internal/workers/heartbeat','workerHeartbeat','Ack',{request:'WorkerHeartbeat',role:'worker'});
// Normalize refs introduced in parameters after component generation.
api.paths=apiConvert(api.paths);
const U=i=>`${String(i).padStart(8,'0')}-0000-4000-8000-000000000001`;
const now='2026-10-15T00:00:00Z';
const initial='9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9';
const P={BLUE:{team:'doi-a',submission_id:U(3)},RED:{team:'doi-b',submission_id:U(4)}};
const examples={
 User:{id:U(1),email:'captain@example.test',role:'captain',team_id:U(2),is_active:true},
 TeamPublic:{id:U(2),name:'Đội A',slug:'doi-a'},
 Result:{winner:'RED',reason:'CRASH',plies:0},
 GameConfig:{engine_version:'1.0.0',ruleset_id:'dev-v1',map_id:'standard',initial_fen:initial,players:P,budget_ms:60000,init_ms:10000,grace_ms:50,hard_timeout_extra_ms:1000,max_turns:300,seed:42},
 BuildJob:{schema_version:1,job_id:U(5),submission_id:U(3),language:'python',source_key:`submissions/${U(3)}/source.zip`,source_sha256:'a'.repeat(64),engine_version:'1.0.0'},
 BuildResult:{schema_version:1,job_id:U(5),submission_id:U(3),status:'ready',image_tag:`registry.local/ottv2-bot@sha256:${'a'.repeat(64)}`,build_log_key:`staging/${U(5)}/${U(12)}/builds/${U(3)}/build.log`,error:null},
 Replay:{format:1,engine_version:'1.0.0',ruleset_id:'dev-v1',map_id:'standard',initial_fen:initial,players:{BLUE:{...P.BLUE,bot_name:'ExampleBlue'},RED:{...P.RED,bot_name:'ExampleRed'}},moves:[],result:{winner:'RED',reason:'CRASH',plies:0}},
 WsEvent:{schema_version:1,event_id:U(6),type:'build.updated',channel:`team:${U(2)}`,occurred_at:now,data:{submission_id:U(3),status:'ready'}},
 WorkerHeartbeat:{worker_id:'match-1',kind:'match',job_id:null,sent_at:now},
 SignedUrl:{url:'http://127.0.0.1:4010/fixtures/replay.json',expires_at:'2099-01-01T00:00:00Z'},
 Error:{error:{code:'INVALID_REQUEST',message:'Dữ liệu không hợp lệ',details:{}},request_id:U(9)},
 Capabilities:{contract_version:'1.3.0',languages:['python','cpp'],max_upload_bytes:1048576,max_files:50,ruleset_id:'dev-v1',ruleset_status:'development',tournament_enabled:false},
 Auth:{access_token:'mock-captain-token',token_type:'bearer',expires_in:900,user:null},
 TeamCreate:{name:'Đội A',slug:'doi-a',captain_email:'captain@example.test',seed:1},
 AdminTeamPatch:{status:'approved',reason:'Duyệt đội'},
 SourceFile:{submission_id:U(3),path:'main.py',content:'# example bot\n',truncated:false},
 SourceTree:{submission_id:U(3),files:[{path:'main.py',size_bytes:14,language:'python'}]},
 ImportRequest:{csv:'name,slug,captain_email,seed\nĐội A,doi-a,captain@example.test,1\n'},
 Docs:{rules_markdown:'dev-v1: xem contracts/rules.md; chưa phải luật thi đấu chính thức.',protocol_markdown:'OTTV2 1 → READY → INIT → OK → STATE / GO → MOVE → END',starter_kits:[]}
};
examples.Auth.user=examples.User;
examples.MatchJob={schema_version:1,job_id:U(7),game_id:U(8),attempt:1,blue_image:examples.BuildResult.image_tag,red_image:`registry.local/ottv2-bot@sha256:${'b'.repeat(64)}`,map_id:'standard',engine_version:'1.0.0',players:P,config:examples.GameConfig};
examples.GameResultCallback={schema_version:1,job_id:U(7),game_id:U(8),attempt:1,status:'finished',result:examples.Result,replay_key:`staging/${U(7)}/${U(12)}/games/${U(8)}/replay.json.gz`,log_key:`staging/${U(7)}/${U(12)}/games/${U(8)}/`,duration_ms:20,error:null};
examples.EngineResult={...examples.Result,duration_ms:20,replay:examples.Replay};
examples.Team={...examples.TeamPublic,status:'approved',is_locked:false,seed:1,group_id:null,members:[examples.User],active_bots:[{team_id:U(2),scope:'scrimmage',submission_id:U(3)}]};
examples.Game={id:U(8),match_id:U(10),game_index:1,attempt:1,is_current:true,blue_submission_id:U(3),red_submission_id:U(4),map_id:'standard',engine_version:'1.0.0',ruleset_id:'dev-v1',status:'finished',result:examples.Result,duration_ms:20,replay_available:true};
examples.Match={id:U(10),tournament_id:null,round_id:null,stage:'scrimmage',team_a:examples.TeamPublic,team_b:{id:U(11),name:'Đội B',slug:'doi-b'},best_of:'two_games',status:'running',winner_team_id:null,score_a:0,score_b:1,games:[examples.Game]};
examples.Submission={id:U(3),team_id:U(2),language:'python',status:'ready',sha256:'a'.repeat(64),submitted_at:now,build_error:null};
examples.Quota={limit:60,used:1,remaining:59,resets_at:'2026-10-15T17:00:00Z',active:1,active_limit:2,admission:{accepting:true,paused_reason:null}};
function sample(schema,name=''){
 if(schema.$ref){const name=schema.$ref.split('/').pop();return structuredClone(examples[name]??sample(D[name],name));}
 if('const'in schema)return schema.const;
 if(schema.enum)return schema.enum[0];
 if(schema.oneOf)return sample(schema.oneOf[0],name);
 if(schema.anyOf){const branch=schema.anyOf.find(x=>x.type==='null');return branch?null:sample(schema.anyOf[0],name);}
 if(schema.type==='object')return Object.fromEntries((schema.required??[]).map(k=>[k,sample(schema.properties[k],k)]));
 if(schema.type==='array')return [];
 if(schema.type==='integer'||schema.type==='number')return schema.minimum??0;
 if(schema.type==='boolean')return false;
 if(schema.type==='null')return null;
 if(schema.format==='uuid')return U(1);
 if(schema.format==='date-time')return now;
 if(schema.format==='email')return 'member@example.test';
 if(schema.format==='uri')return 'https://example.test/fixture';
 if(schema.pattern){if(schema.pattern.includes('team:'))return `team:${U(2)}`;if(schema.pattern==='^#')return '# debug';if(schema.pattern.includes('{64}'))return 'a'.repeat(64);if(schema.pattern.includes('[BPK'))return initial;if(schema.pattern.includes('[a-i]'))return 'c3d4';if(schema.pattern.includes('[0-9]+'))return '1.0.0';return 'example';}
 return 'example';
}
examples.Register={email:'new-captain@example.test',password:'example-password',team_name:'Đội mới'};
examples.ProfileEdit={display_name:'Người chơi OTT',bio:'Hẹn gặp trên bàn cờ!',avatar:'fox',frame:'bronze',color:'amber'};
examples.Profile={user_id:U(1),...examples.ProfileEdit,stats:{played:0,wins:0,losses:0,by_map:['standard','hexagon','circular'].map(map=>({map,played:0,wins:0,losses:0}))}};
examples.RoomJoin={code:'ABCDEFGH'};
examples.Room={id:U(40),code:'ABCDEFGH',map:'standard',revision:0,round:1,status:'waiting',players:[{id:U(1),side:'BLUE',ready:false,rematch:false}],fen:'9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9',position:{},turn:null,moves:[],legal_moves:[],result:null};
examples.RoomList=[examples.Room];
for(const name of Object.keys(D))if(!(name in examples))examples[name]=sample(D[name],name);
for(const name of Object.keys(D).filter(x=>x.endsWith('Page'))){examples[name]={items:[examples[name.slice(0,-4)]],page:1,page_size:20,total:1};}
// Useful UI examples override empty collections without claiming tournament execution.
examples.Queue={queues:['build','match:tournament','match:scrimmage'].map(name=>({name,paused:false,queued:0,running:0,failed:0})),workers:[{id:'match-1',kind:'match',last_seen_at:now,status:'idle',job_id:null}],scrimmage_admission:{accepting:true,paused_reason:null}};
examples.MatchAccepted={match_id:U(10),status:'queued'};examples.SubmissionAccepted={id:U(3),status:'queued'};
examples.ActiveBot={team_id:U(2),scope:'scrimmage',submission_id:U(3)};
const cases=[];
for(const [file,name] of Object.entries(wrappers)){write(`examples/${file}.json`,examples[name]);cases.push({file:`examples/${file}.json`,schema:`schemas/${file}.schema.json`,valid:true});}
// Status branch fixtures; both positive and negative examples are validated in CI.
function fixture(file,name,value,valid=true,semantic=null){write(`examples/${file}.json`,value);cases.push({file:`examples/${file}.json`,definition:name,valid,...(semantic?{semantic}:{})});}
fixture('scrimmage-paused','Quota',{...examples.Quota,admission:{accepting:false,paused_reason:'tournament_load'}});
fixture('invalid-scrimmage-paused-without-reason','Quota',{...examples.Quota,admission:{accepting:false,paused_reason:null}},false);
fixture('invalid-scrimmage-accepting-with-reason','Quota',{...examples.Quota,admission:{accepting:true,paused_reason:'scrimmage_backlog'}},false);
fixture('invalid-register-password','Register',{...examples.Register,password:'short'},false);
fixture('invalid-profile-avatar','ProfileEdit',{...examples.ProfileEdit,avatar:'https://example.test/avatar.svg'},false);
fixture('invalid-profile-name','ProfileEdit',{...examples.ProfileEdit,display_name:'   '},false);
fixture('invalid-profile-email','ProfileEdit',{...examples.ProfileEdit,email:'private@example.test'},false);
fixture('invalid-register-role','Register',{...examples.Register,role:'admin'},false);
fixture('invalid-register-team','Register',{...examples.Register,team_name:'   '},false);
fixture('build-building','BuildResult',{...examples.BuildResult,status:'building',image_tag:null,build_log_key:null});
fixture('build-failed','BuildResult',{...examples.BuildResult,status:'failed',image_tag:null,error:{code:'COMPILE_ERROR',message:'Compilation failed'}});
fixture('game-running','GameResultCallback',{...examples.GameResultCallback,status:'running',result:null,replay_key:null,log_key:null,duration_ms:0});
fixture('game-infra-error','GameResultCallback',{...examples.GameResultCallback,status:'infra_error',result:null,replay_key:null,log_key:null,error:{code:'INFRA_ERROR',message:'Storage unavailable'}});
fixture('invalid-build-ready','BuildResult',{...examples.BuildResult,image_tag:null},false);
fixture('invalid-game-infra-winner','GameResultCallback',{...examples.GameResultCallback,status:'infra_error',error:{code:'INFRA_ERROR',message:'Unavailable'}},false);
fixture('invalid-language','BuildJob',{...examples.BuildJob,language:'rust'},false);
fixture('invalid-unknown-field','BuildJob',{...examples.BuildJob,source_url:'https://example.test'},false);
fixture('invalid-attempt','GameResultCallback',{...examples.GameResultCallback,attempt:0},false);
fixture('invalid-source-path','BuildJob',{...examples.BuildJob,source_key:'../secret'},false);
for(const branch of D.WsClient.oneOf)fixture('ws-client-'+branch.properties.type.const,'WsClient',sample(branch));
for(const branch of D.WsEvent.oneOf)fixture('event-'+branch.properties.type.const,'WsEvent',sample(branch));
fixture('invalid-public-build-event','WsEvent',{...examples.WsEvent,channel:'public'},false);
fixture('invalid-job-config-mismatch','MatchJob',{...examples.MatchJob,config:{...examples.GameConfig,engine_version:'2.0.0'}},false,'job');
fixture('invalid-id','BuildJob',{...examples.BuildJob,job_id:'not-a-uuid'},false);
const missingJobId={...examples.BuildJob};delete missingJobId.job_id;
fixture('invalid-missing-field','BuildJob',missingJobId,false);
fixture('invalid-finished-game','Game',{...examples.Game,result:null},false);
for(const reason of ['TIMEOUT','ILLEGAL_MOVE','CRASH','MOVE_LIMIT'])fixture('replay-'+reason.toLowerCase(),'Replay',{...examples.Replay,result:{winner:'RED',reason,plies:0}},true,'shape-only');
fixture('invalid-replay-count','Replay',{...examples.Replay,result:{winner:'RED',reason:'CRASH',plies:1}},false,'replay');
fixture('invalid-replay-fen','Replay',{...examples.Replay,initial_fen:'99/9/9/9/9/9/9/9/9'},false,'replay');
function fen(pieces){const rows=[];for(let rank=9;rank>=1;rank--){let row='',empty=0;for(let file=0;file<9;file++){const piece=pieces[String.fromCharCode(97+file)+rank];if(piece){if(empty)row+=empty;empty=0;row+=piece;}else empty++;}if(empty)row+=empty;rows.push(row);}return rows.join('/');}
const boardCases=[
 {id:'step',pieces:{c3:'B',g7:'k'},move:'c3d4',side:'BLUE',legal:true,after:{d4:'B',g7:'k'}},
 {id:'capture-rock-scissors',pieces:{c3:'B',d4:'k',g7:'p'},move:'c3d4',side:'BLUE',legal:true,after:{d4:'B',g7:'p'}},
 {id:'capture-paper-rock',pieces:{c3:'P',d4:'b'},move:'c3d4',side:'BLUE',legal:true,after:{d4:'P'}},
 {id:'capture-scissors-paper',pieces:{c3:'K',d4:'p'},move:'c3d4',side:'BLUE',legal:true,after:{d4:'K'}},
 {id:'friendly-block',pieces:{c3:'B',d4:'P',g7:'k'},move:'c3d4',side:'BLUE',legal:false},
 {id:'same-kind-block',pieces:{c3:'B',d4:'b'},move:'c3d4',side:'BLUE',legal:false},
 {id:'suicide-block',pieces:{c3:'B',d4:'p'},move:'c3d4',side:'BLUE',legal:false},
 {id:'too-far',pieces:{c3:'B',g7:'k'},move:'c3e5',side:'BLUE',legal:false},
 {id:'blue-forbidden-goal',pieces:{b2:'B',g7:'k'},move:'b2a1',side:'BLUE',legal:false},
 {id:'blue-goal',pieces:{h8:'B',a8:'k'},move:'h8i9',side:'BLUE',legal:true,after:{i9:'B',a8:'k'}},
 {id:'red-goal',pieces:{b2:'b',g7:'K'},move:'b2a1',side:'RED',legal:true,after:{a1:'b',g7:'K'}},
 {id:'red-forbidden-goal',pieces:{h8:'b',a8:'K'},move:'h8i9',side:'RED',legal:false}
].map(({pieces,after,...c})=>({...c,initial_fen:fen(pieces),expected_fen:after?fen(after):fen(pieces)}));
write('fixtures/board-cases.json',{ruleset_id:'dev-v1',status:'development',cases:boardCases});
// Published draw test vector for all languages: xorshift32 + unbiased shuffle.
function draw(seed,count){let state=seed>>>0;const next=()=>{state^=state<<13;state^=state>>>17;state^=state<<5;return state>>>0;};const bounded=bound=>{const limit=Math.floor(4294967296/bound)*bound;let value;do{value=next();}while(value>=limit);return value%bound;};const groups={A:[],B:[],C:[],D:[]};for(let start=1;start<=count;start+=4){const pot=[start,start+1,start+2,start+3];for(let i=3;i>0;i--){const j=bounded(i+1);[pot[i],pot[j]]=[pot[j],pot[i]];}Object.keys(groups).forEach((label,i)=>groups[label].push(pot[i]));}return groups;}
write('fixtures/draw-cases.json',{ruleset_id:'dev-v1',algorithm:'xorshift32-fisher-yates-rejection-v1',cases:[{seed:42,team_count:20,groups:draw(42,20)},{seed:42,team_count:8,groups:draw(42,8)},{seed:1,team_count:20,groups:draw(1,20)}]});
const stepReplay={...examples.Replay,moves:[{ply:1,side:'BLUE',move:'c3d4',think_ms:70,clock_ms:59980,capture:null,debug:['# fixture']},{ply:2,side:'RED',move:'g7f6',think_ms:80,clock_ms:59970,capture:null,debug:[]}],result:{winner:'RED',reason:'CRASH',plies:2}};
fixture('replay-two-moves','Replay',stepReplay,true,'replay');
const cap=boardCases.find(c=>c.id==='capture-rock-scissors');
fixture('replay-capture','Replay',{...examples.Replay,initial_fen:cap.initial_fen,moves:[{ply:1,side:'BLUE',move:cap.move,think_ms:70,clock_ms:59980,capture:'k',debug:[]}],result:{winner:'BLUE',reason:'CRASH',plies:1}},true,'replay');
const goal=boardCases.find(c=>c.id==='blue-goal');
fixture('replay-goal','Replay',{...examples.Replay,initial_fen:goal.initial_fen,moves:[{ply:1,side:'BLUE',move:goal.move,think_ms:70,clock_ms:59980,capture:null,debug:[]}],result:{winner:'BLUE',reason:'GOAL',plies:1}},true,'replay');
fixture('invalid-replay-capture','Replay',{...stepReplay,moves:[{...stepReplay.moves[0],capture:'k'},stepReplay.moves[1]]},false,'replay');
const index=[];
for(const operation of operations){
 const o=api.paths[operation.path][operation.method];
 const record={...operation};
 if(operation.request){const file=`examples/http/${operation.operationId}.request.json`;write(file,examples[operation.request]);record.request_example=file;cases.push({file,definition:operation.request,valid:true});o.requestBody.content[operation.multipart?'multipart/form-data':'application/json'].example=examples[operation.request];}
 if(operation.response){const file=`examples/http/${operation.operationId}.response.json`;write(file,examples[operation.response]);record.response_example=file;cases.push({file,definition:operation.response,valid:true});o.responses[operation.status].content['application/json'].example=examples[operation.response];}
 index.push(record);
}
// Minimal generated wire types. Runtime validation remains JSON Schema's job.
function ts(x){
 if(x.$ref)return x.$ref.split('/').pop();
 if('const'in x)return JSON.stringify(x.const);
 if(x.enum)return x.enum.map(JSON.stringify).join(' | ');
 if(x.oneOf||x.anyOf)return (x.oneOf??x.anyOf).map(v=>`(${ts(v)})`).join(' | ');
 if(x.type==='null')return 'null';if(x.type==='boolean')return 'boolean';
 if(x.type==='integer'||x.type==='number')return 'number';
 if(x.type==='array')return `Array<${ts(x.items)}>`;
 if(x.type==='object'){if(!x.properties)return `Record<string, ${typeof x.additionalProperties==='object'?ts(x.additionalProperties):'unknown'}>`;return '{ '+Object.entries(x.properties).map(([k,v])=>`${JSON.stringify(k)}${x.required?.includes(k)?'':'?'}: ${ts(v)}`).join('; ')+' }';}
 return 'string';
}
output('generated/types.ts','// GENERATED by node contracts/build.mjs. Do not edit. Wire types only.\n'+Object.entries(D).map(([name,value])=>`export type ${name} = ${ts(value)};`).join('\n')+'\n');
output('generated/operations.ts','// GENERATED. Use with your shared authenticated HTTP transport.\nimport type * as T from "./types";\nexport interface Operations {\n'+operations.map(o=>`  ${o.operationId}: { request: ${o.request?'T.'+o.request:'undefined'}; response: ${o.response?'T.'+o.response:'undefined'} };`).join('\n')+'\n}\nexport const routes = '+JSON.stringify(Object.fromEntries(operations.map(o=>[o.operationId,{method:o.method.toUpperCase(),path:o.path,status:o.status}])) ,null,2)+' as const;\n');
// Upload is added after the initial schema list, so write common last.
write('schemas/common.schema.json',{$schema:'https://json-schema.org/draft/2020-12/schema',$defs:D});
write('openapi.yaml',api);write('operations.json',index);write('examples/manifest.json',cases);
write('version.json',{contract_version:'1.3.0',schema_version:1,replay_format:1,protocol_version:1,ruleset_id:'dev-v1',ruleset_status:'development'});
console.log(`Generated ${Object.keys(D).length} definitions, ${operations.length} operations, ${cases.length} fixture cases.`);
