/* 引擎回归用例：改完 src/engine.js 跑一次，确认没把日历和发薪日算坏。
   node tests/engine.test.js */

var assert = require('assert');
var path = require('path');
var G = require(path.join(__dirname, '..', 'src', 'engine.js'));

var pass = 0, fail = 0;

function t(name, fn) {
  try {
    fn();
    pass++;
    console.log('  ok   ' + name);
  } catch (e) {
    fail++;
    console.log('  FAIL ' + name + '\n       ' + (e && e.message));
  }
}

// 同一天里逐秒比对用
function at(y, m, d, h, mi, s) { return new Date(y, m - 1, d, h || 0, mi || 0, s || 0); }
function fmt(d) {
  if (!d) return 'null';
  var p = function (n) { return String(n).padStart(2, '0'); };
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
    + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}

function engine(extra) {
  var base = {
    monthly_salary: 8000,
    work_start: '09:00', work_end: '18:00',
    break_start: '12:00', break_end: '13:00',
    pay_day: 5, pay_time: '17:00'
  };
  for (var k in extra) base[k] = extra[k];
  return new G.Engine(G.normalize(base));
}

console.log('发薪日');
t('11-04 21:00 之后的下一个是 11-05 17:00', function () {
  var e = engine();
  assert.strictEqual(fmt(e.snapshot(at(2026, 11, 4, 21, 0), false).payday), '2026-11-05 17:00');
});

t('5 号落周六就往前挪到 12-04 周五', function () {
  var e = engine();
  assert.strictEqual(fmt(e.snapshot(at(2026, 12, 1, 9, 0), false).payday), '2026-12-04 17:00');
});

t('整段国庆假期把 10-05 退到 09-30', function () {
  var e = engine();
  assert.strictEqual(fmt(e.snapshot(at(2026, 9, 29, 9, 0), false).payday), '2026-09-30 17:00');
});

t('退到的日子已经过去，就跳到下个月（不倒计时到过去）', function () {
  var e = engine();
  assert.strictEqual(fmt(e.snapshot(at(2026, 10, 1, 9, 0), false).payday), '2026-11-05 17:00');
});

t('当天已过点就跳下个月', function () {
  var e = engine();
  var s = e.snapshot(at(2026, 11, 5, 17, 0, 1), false);
  assert.ok(s.payday.getTime() > at(2026, 11, 5, 17, 0, 1).getTime(), '应该已经跳到下个月');
  assert.strictEqual(s.payday.getMonth(), 11, '应落在 12 月，实际 ' + fmt(s.payday));
});

t('2 月没有 31 号，按当月末算且不跑出这个月', function () {
  var e = engine({ pay_day: 31 });
  var s = e.snapshot(at(2026, 2, 1, 9, 0), false);
  assert.strictEqual(s.payday.getMonth(), 1, '应仍在 2 月，实际 ' + fmt(s.payday));
  assert.strictEqual(s.payday.getDate() >= 24, true, '应接近月末，实际 ' + fmt(s.payday));
});

t('留空发薪日就没有下一个发薪时刻', function () {
  var e = engine({ pay_day: 0, pay_time: '' });
  var s = e.snapshot(at(2026, 11, 4, 21, 0), false);
  assert.strictEqual(s.payday, null);
  assert.strictEqual(s.paydayLeft, 0);
});

console.log('计时口径');
t('午休期间 worked 不动，clockLeft 照常走', function () {
  var a = engine().snapshot(at(2026, 11, 4, 12, 30, 0), false);
  var b = engine().snapshot(at(2026, 11, 4, 12, 30, 20), false);
  assert.strictEqual(a.worked, b.worked, '午休不该累计工时');
  assert.ok(Math.abs((a.clockLeft - b.clockLeft) - 20) < 0.001, '离下班时钟应少 20 秒');
});

t('12:30 的工时进度仍是 3/8，时间轴进度按上下班跨度算', function () {
  var s = engine().snapshot(at(2026, 11, 4, 12, 30), false);
  assert.ok(Math.abs(s.progress - 0.375) < 1e-9, '净工时进度 ' + s.progress);
  assert.ok(Math.abs(s.spanProgress - 3.5 / 9) < 1e-9, '时间轴进度 ' + s.spanProgress);
  assert.strictEqual(s.worked, 10800);
  assert.strictEqual(s.totalSec, 28800);
});

t('下班后 worked 顶到满、clockLeft 归零', function () {
  var s = engine().snapshot(at(2026, 11, 4, 20, 0), false);
  assert.strictEqual(s.worked, 28800);
  assert.strictEqual(s.clockLeft, 0);
});

t('休息日不累计工时', function () {
  var s = engine().snapshot(at(2026, 11, 7, 12, 0), false);   // 周六
  assert.strictEqual(s.isWorkday, false);
  assert.strictEqual(s.worked, 0);
});

console.log('节假日与调休');
t('默认配置内置 2026 年 6 天官方补班日', function () {
  assert.deepStrictEqual(G.defaults().makeup_workdays, [
    '2026-01-04', '2026-02-14', '2026-02-28',
    '2026-05-09', '2026-09-20', '2026-10-10'
  ]);
});

t('10-10（周六）和 9-20（周日）算工作日', function () {
  var cal = new G.WorkCalendar(G.normalize(G.defaults()));
  assert.strictEqual(cal.isWorkday(at(2026, 10, 10)), true);
  assert.strictEqual(cal.isWorkday(at(2026, 9, 20)), true);
});

t('春节 2/23 放假、2/28 补班都按官方通知算', function () {
  var cal = new G.WorkCalendar(G.normalize(G.defaults()));
  assert.strictEqual(cal.isWorkday(at(2026, 2, 23)), false);
  assert.strictEqual(cal.isWorkday(at(2026, 2, 28)), true);
});

console.log('格式');
t('parseHHMM 认得出正常值、拒绝脏值', function () {
  assert.deepStrictEqual(G.parseHHMM('09:05'), { h: 9, mi: 5 });
  assert.strictEqual(G.parseHHMM('25:00'), null);
  assert.strictEqual(G.parseHHMM(''), null);
});

t('normalize 把越界的发薪日拉回默认', function () {
  assert.strictEqual(G.normalize({ pay_day: 32 }).pay_day, 5);
  assert.strictEqual(G.normalize({ pay_day: 0 }).pay_day, 0);
  assert.strictEqual(G.normalize({ pay_day: '' }).pay_day, 0);
});

console.log('桌面选项');
var fs = require('fs');
var uiSrc = fs.readFileSync(path.join(__dirname, '..', 'src', 'ui.js'), 'utf8');
t('四个桌面开关都在 change 时即时落库', function () {
  ['autostart', 'check_update', 'notify_schedule', 'close_exit'].forEach(function (k) {
    assert.ok(uiSrc.indexOf("deskChanged('" + k + "'") >= 0, k + ' 没有即时保存');
  });
});
t('异步回填不覆盖用户刚改过的选项，且旧响应被丢弃', function () {
  assert.ok(uiSrc.indexOf('deskTouched[key] = true') >= 0, '未标记改动项');
  assert.ok(uiSrc.indexOf('if (seq === deskReq)') >= 0, '未防陈旧响应');
  assert.ok(uiSrc.indexOf('if (!deskTouched.close_exit)') >= 0, '回填未跳过改动项');
});
t('保存按钮仍兜底写一次桌面选项', function () {
  assert.ok(uiSrc.indexOf('saveDeskOpts();') >= 0);
});

console.log('轻量模式');
var deskSrc = fs.readFileSync(path.join(__dirname, '..', 'desktop.py'), 'utf8');
var cssSrc = fs.readFileSync(path.join(__dirname, '..', 'src', 'app.css'), 'utf8');
t('桌面层在收托盘/最小化时休眠、显示时唤醒', function () {
  assert.ok(deskSrc.indexOf('Guliqi.sleepUI()') >= 0);
  assert.ok(deskSrc.indexOf('Guliqi.wakeUI()') >= 0);
  assert.ok(deskSrc.indexOf('window.events.minimized += on_minimized') >= 0);
  assert.ok(deskSrc.indexOf('window.events.restored += on_restored') >= 0);
});
t('CSS 全局停动画并隐藏场景层', function () {
  assert.ok(cssSrc.indexOf('html.sleeping *') >= 0);
  assert.ok(cssSrc.indexOf('html.sleeping .fx') >= 0);
});
t('页面休眠保留通知心跳、唤醒重启帧循环', function () {
  assert.ok(uiSrc.indexOf('trackPhase(engine.snapshot(nowAt(), cfg.demo))') >= 0);
  assert.ok(uiSrc.indexOf('if (running && raf === null) loop()') >= 0);
  assert.ok(uiSrc.indexOf('G.fxSleep = function') >= 0);
});

console.log('全屏');
var headSrc = fs.readFileSync(path.join(__dirname, '..', 'src', 'index.html'), 'utf8');
t('顶栏有全屏按钮，两套图标按状态切换', function () {
  assert.ok(headSrc.indexOf('id="btnFullscreen"') >= 0);
  assert.ok(cssSrc.indexOf('html.fullscreen #btnFullscreen .i-compress') >= 0);
});
t('F11 与按钮都调桌面层全屏', function () {
  assert.ok(uiSrc.indexOf("e.key === 'F11'") >= 0);
  assert.ok(uiSrc.indexOf("desk.call('toggle_fullscreen')") >= 0);
});
t('全屏期间不把整块屏幕记成窗口尺寸', function () {
  assert.ok(deskSrc.indexOf('if win is None or state.fullscreen') >= 0);
  assert.ok(deskSrc.indexOf('if state.fullscreen or time.time() < state.fit_until') >= 0);
});

console.log('');
console.log(fail === 0 ? ('全部通过：' + pass + ' 项') : ('失败 ' + fail + ' 项 / 共 ' + (pass + fail) + ' 项'));
process.exit(fail === 0 ? 0 : 1);
