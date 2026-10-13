const {test}=require('node:test');const assert=require('node:assert/strict');const rules=require('../mobile/assets/run-rules.js');
const at=(h,m=0)=>new Date(2026,9,6,h,m);
test('有效时段边界和中间休息时段',()=>{for(const [h,m,v] of [[5,59,false],[6,0,true],[16,59,true],[17,0,false],[18,59,false],[19,0,true],[21,59,true],[22,0,false]])assert.equal(rules.inWindow(at(h,m)),v);});
test('3公里时长阈值',()=>{assert.equal(rules.durationLimit(3),3600);assert.equal(rules.durationLimit(3.001),7200);});
test('自动闭合和整圈目标，默认6分配速',()=>{const p=rules.plan([{lat:30,lon:120},{lat:30.001,lon:120}],3.2,6);assert.equal(p.loops,15);assert.ok(p.total>=3.2&&p.total<3.5);assert.ok(Math.abs(p.speed-25/9)<1e-10);assert.ok(Math.abs(p.seconds-p.total*360)<1e-10);});
test('整圈超过上限可检测，重复点不能启动',()=>{assert.equal(rules.plan([{lat:30,lon:120},{lat:30.05,lon:120}],3.2,6).overLimit,true);assert.throws(()=>rules.plan([{lat:30,lon:120},{lat:30,lon:120}],3.2,6));});
test('拒绝无效距离或配速',()=>{for(const [km,pace] of [[2,6],[11,6],[3,2],[3,11],[NaN,6]])assert.throws(()=>rules.plan([],km,pace));});
