/* ==ENGINE-START== */
var Guliqi = (function () {
  'use strict';

  var STORE_KEY = 'guliqi.cfg.v1';
  var READY_KEY = 'guliqi.ready.v1';   // 只有真的设置过才写，用来判定"首次进入"

  // 中性兜底值：仅用于字段预填和异常回退，不是任何人的真实数据
  var DEFAULT_CFG = {
    version: 1,
    monthly_salary: 8000,
    work_start: '09:00',
    work_end: '18:00',
    break_start: '12:00',
    break_end: '13:00',
    // 发薪日：每月几号、几点到账。碰上周末或节假日会往前挪到最近的工作日。
    // pay_day = 0 表示用户留空：不显示发薪倒计时（配置里可以是"没有这项"）
    pay_day: 5,
    pay_time: '17:00',
    work_weekdays: [1, 2, 3, 4, 5],
    holidays: [
      // ---- 2026 ----
      '2026-01-01', '2026-01-02', '2026-01-03',
      '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19',
      '2026-02-20', '2026-02-21', '2026-02-22',
      '2026-04-04', '2026-04-05', '2026-04-06',
      '2026-05-01', '2026-05-02', '2026-05-03', '2026-05-04', '2026-05-05',
      '2026-06-19', '2026-06-20', '2026-06-21',
      '2026-09-25', '2026-09-26', '2026-09-27',
      '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04',
      '2026-10-05', '2026-10-06', '2026-10-07',
      // ---- 2027 ----
      // 元旦 1/1（周五）连周末，不调休
      '2027-01-01', '2027-01-02', '2027-01-03',
      // 春节 除夕 2/5（周五）起连休，与周末顺连共 9 天
      '2027-02-05', '2027-02-06', '2027-02-07', '2027-02-08', '2027-02-09',
      '2027-02-10', '2027-02-11', '2027-02-12', '2027-02-13',
      // 清明 4/3-4/5，不调休
      '2027-04-03', '2027-04-04', '2027-04-05',
      // 劳动节 4/30-5/4，调休 1 天
      '2027-04-30', '2027-05-01', '2027-05-02', '2027-05-03', '2027-05-04',
      // 端午 6/9（周三）、中秋 9/15（周三），各放 1 天不调休
      '2027-06-09',
      '2027-09-15',
      // 国庆 10/1-10/7，调休 2 天
      '2027-10-01', '2027-10-02', '2027-10-03', '2027-10-04',
      '2027-10-05', '2027-10-06', '2027-10-07'
    ],
    // 调休补班日没有统一答案（各公司排班不同），留空让你自己补。
    // 空数组是安全的：日历会照常按周末+节假日推算，不会报错。
    makeup_workdays: [],
    items: [
      { name: '一瓶农夫山泉', price: 2 },
      { name: '一根烤肠', price: 3 },
      { name: '一杯蜜雪冰城柠檬水', price: 4 },
      { name: '一份煎饼果子', price: 8 },
      { name: '一杯瑞幸', price: 9.9 },
      { name: '一支牙膏', price: 10 },
      { name: '一根数据线', price: 15 },
      { name: '一杯霸王茶姬', price: 20 },
      { name: '一个手机壳', price: 20 },
      { name: '一杯星巴克', price: 30 },
      { name: '一份麻辣烫', price: 30 },
      { name: '一瓶洗发水', price: 30 },
      { name: '一把雨伞', price: 35 },
      { name: '一袋咖啡豆', price: 70 },
      { name: '一件 T 恤', price: 99 },
      { name: '一个充电宝', price: 120 },
      { name: '一个吹风机', price: 190 },
      { name: '一件卫衣', price: 200 },
      { name: '一顿火锅', price: 220 },
      { name: '一条工装裤', price: 250 },
      { name: '一双运动鞋', price: 300 },
      // 往上是给日薪更高的人准备的。日薪 1000+ 的话，300 块的鞋上午就到了，
      // 下午得有更贵的目标才有盼头，所以 400–10000 按阶梯补了一批。
      { name: '一顿双人火锅', price: 400 },
      { name: '一双入门跑鞋', price: 500 },
      { name: '一顿日料放题', price: 600 },
      { name: '一副无线耳机', price: 800 },
      { name: '一件羽绒服', price: 999 },
      { name: '一双好球鞋', price: 1200 },
      { name: '一个机械键盘', price: 1500 },
      { name: '一台平板', price: 2500 },
      { name: '一部手机', price: 4000 },
      { name: '一台笔记本', price: 7000 },
      { name: '一次旅行', price: 10000 }
    ],
    display: { hide_money: false },
    theme: 'system',   // 见 THEME_LIST：三个默认值 + 五个彩色主题
    demo: false,
    demo_offset: 0     // 演示时钟相对真实时间的偏移（毫秒），0 = 不偏移
  };

  // 彩色主题清单（8 套）：极光夜 / 樱花粉 / 落日橙 / 薄荷绿 / 星河紫 / 深海蓝 / 水墨 / 霓虹夜。
  // 随返回对象导出，head 防闪脚本、ui.js、store.py 的名单都要与这里同步。
  var THEME_LIST = {
    system: 1, light: 1, dark: 1,
    aurora: 1, sakura: 1, sunset: 1, mint: 1, galaxy: 1,
    ocean: 1, ink: 1, neon: 1
  };

  /* ---------- 小工具 ---------- */
  function p2(n) { return String(n).padStart(2, '0'); }

  function isoOf(d) {
    return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate());
  }

  function toNum(v, def) {
    if (def === undefined) def = 0;
    if (typeof v === 'number') return isFinite(v) ? v : def;
    var s = (v === null || v === undefined) ? '' : String(v);
    var n = parseFloat(s.replace(/[,，\s￥¥元]/g, ''));
    return isFinite(n) ? n : def;
  }

  function parseHHMM(v) {
    var m = /^(\d{1,2})[:：](\d{1,2})$/.exec(String(v === null || v === undefined ? '' : v).trim());
    if (!m) return null;
    var h = parseInt(m[1], 10), mi = parseInt(m[2], 10);
    if (!(h >= 0 && h <= 23 && mi >= 0 && mi <= 59)) return null;
    return { h: h, mi: mi };
  }

  function normTime(v, def) {
    var t = parseHHMM(v);
    return t ? p2(t.h) + ':' + p2(t.mi) : def;
  }

  function normTimeOpt(v) {
    if (v === null || v === undefined) return '';
    var s = String(v).trim();
    if (!s || s === '-' || s === '无') return '';
    var t = parseHHMM(s);
    return t ? p2(t.h) + ':' + p2(t.mi) : '';
  }

  function parseWeekdays(v) {
    var parts = [];
    if (typeof v === 'number') parts = [v];
    else if (typeof v === 'string') parts = v.split(/[,，、\s]+/).filter(Boolean);
    else if (Array.isArray(v)) parts = v;
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var n = parseInt(parts[i], 10);
      if (n >= 1 && n <= 7 && out.indexOf(n) < 0) out.push(n);
    }
    out.sort(function (a, b) { return a - b; });
    return out.length ? out : [1, 2, 3, 4, 5];
  }

  function parseDates(v) {
    var parts = [];
    if (Array.isArray(v)) parts = v.map(String);
    else if (typeof v === 'string') parts = v.split(/[,，、\s]+/).filter(Boolean);
    var out = [], seen = {};
    for (var i = 0; i < parts.length; i++) {
      var m = /^(\d{4})[-\/.](\d{1,2})[-\/.](\d{1,2})$/.exec(String(parts[i]).trim());
      if (!m) continue;
      var y = +m[1], mo = +m[2], d = +m[3];
      var dt = new Date(y, mo - 1, d);
      if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) continue;
      var k = isoOf(dt);
      if (!seen[k]) { seen[k] = 1; out.push(k); }
    }
    out.sort();
    return out;
  }

  function parseItems(v) {
    var out = [];
    function push(name, price) {
      name = String(name === undefined || name === null ? '' : name).trim();
      var p = toNum(price, 0);
      if (name && p > 0) out.push({ name: name, price: p });
    }
    if (Array.isArray(v)) {
      for (var i = 0; i < v.length; i++) {
        var it = v[i];
        if (typeof it === 'string') {
          var parts = it.split(/[,，\t]/);
          if (parts.length >= 2) push(parts[0], parts[1]);
        } else if (it && typeof it === 'object') {
          push(it.name, it.price);
        }
      }
    } else if (typeof v === 'string') {
      var lines = v.split(/\r?\n/);
      for (var j = 0; j < lines.length; j++) {
        var ln = lines[j].trim();
        if (!ln) continue;
        var seg = ln.split(/[,，\t]/);
        if (seg.length >= 2) push(seg[0], seg[1]);
      }
    }
    if (!out.length) return DEFAULT_CFG.items.slice();
    return out;
  }

  function normalize(raw) {
    var cfg = JSON.parse(JSON.stringify(DEFAULT_CFG));
    if (raw && typeof raw === 'object') {
      for (var k in cfg) {
        if (Object.prototype.hasOwnProperty.call(raw, k) && raw[k] !== undefined) cfg[k] = raw[k];
      }
    }
    cfg.monthly_salary = Math.max(0, toNum(cfg.monthly_salary, 0));
    cfg.work_start = normTime(cfg.work_start, '09:00');
    cfg.work_end = normTime(cfg.work_end, '18:00');
    cfg.break_start = normTimeOpt(cfg.break_start);
    cfg.break_end = normTimeOpt(cfg.break_end);
    /* 发薪日留空是合法状态：pay_day = 0 且 pay_time = ''，主界面那一行直接不出现。
       0 / null / '' 都算留空；只有真的给了一个数才按 1-31 校验，
       超出范围（32、"5 号"）说明是脏数据，退回默认的 5 号。 */
    var pdRaw = cfg.pay_day;
    var pdBlank = (pdRaw === null || pdRaw === undefined || pdRaw === '' ||
                   pdRaw === 0 || pdRaw === '0' || pdRaw === false);
    if (pdBlank) {
      cfg.pay_day = 0;
      cfg.pay_time = '';
    } else {
      cfg.pay_day = Math.round(toNum(pdRaw, DEFAULT_CFG.pay_day));
      if (!(cfg.pay_day >= 1 && cfg.pay_day <= 31)) cfg.pay_day = DEFAULT_CFG.pay_day;
      cfg.pay_time = normTime(cfg.pay_time, DEFAULT_CFG.pay_time);
    }
    cfg.work_weekdays = parseWeekdays(cfg.work_weekdays);
    cfg.holidays = parseDates(cfg.holidays);
    cfg.makeup_workdays = parseDates(cfg.makeup_workdays);
    cfg.items = parseItems(cfg.items);
    cfg.demo = !!cfg.demo;
    // 主题白名单：三个默认值 + 五个彩色主题，脏数据一律退回跟随系统
    cfg.theme = THEME_LIST[cfg.theme] ? cfg.theme : 'system';
    // 偏移限制在 ±2 天内，防止脏数据把时钟甩到离谱的年份
    cfg.demo_offset = Math.max(-172800000, Math.min(172800000, Math.round(toNum(cfg.demo_offset, 0))));
    if (!cfg.demo) cfg.demo_offset = 0;
    var disp = (cfg.display && typeof cfg.display === 'object') ? cfg.display : {};
    cfg.display = { hide_money: !!disp.hide_money };
    return cfg;
  }

  var memStore = null;   // localStorage 不可用时的兜底（file:// 或隐私模式）
  var memReady = false;

  // 是否已经完成过首次设置。没有这个标记 = 首次进入，必须先设置再计算。
  function hasSaved() {
    try { if (localStorage.getItem(READY_KEY) === '1') return true; } catch (e) {}
    return memReady;
  }

  function markReady() {
    memReady = true;
    try { localStorage.setItem(READY_KEY, '1'); } catch (e) {}
  }

  function resetSaved() {
    memReady = false;
    memStore = null;
    try { localStorage.removeItem(READY_KEY); localStorage.removeItem(STORE_KEY); } catch (e) {}
  }

  function loadCfg() {
    var raw = null, s = null;
    try { s = localStorage.getItem(STORE_KEY); } catch (e) { s = null; }
    if (!s) s = memStore;
    if (s) { try { raw = JSON.parse(s); } catch (e2) { raw = null; } }
    return normalize(raw);
  }

  function saveCfg(cfg) {
    var json = JSON.stringify(cfg);
    memStore = json;
    try { localStorage.setItem(STORE_KEY, json); } catch (e) { /* 忽略，用内存兜底 */ }
  }

  /* ---------- 格式化（与 CLI 版逐字一致） ---------- */
  function fmtMoney(v) {
    var neg = v < 0;
    var s = Math.abs(v).toFixed(4);
    var parts = s.split('.');
    var i = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (neg ? '-' : '') + '￥' + i + '.' + parts[1];
  }

  function fmtNum(v) {
    var s = Math.abs(v).toFixed(4);
    var parts = s.split('.');
    var i = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (v < 0 ? '-' : '') + i + '.' + parts[1];
  }

  function fmtHMSms(sec) {
    if (!(sec > 0)) sec = 0;
    var totalMs = Math.floor(sec * 1000);
    var ms = totalMs % 1000;
    var totalS = Math.floor(totalMs / 1000);
    var h = Math.floor(totalS / 3600);
    var mi = Math.floor((totalS % 3600) / 60);
    var s = totalS % 60;
    return p2(h) + ':' + p2(mi) + ':' + p2(s) + '.' + String(ms).padStart(3, '0');
  }

  function fmtDur(sec) {
    var t = Math.max(0, Math.floor(sec));
    if (t < 60) return t + ' 秒';
    var h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60);
    if (h) return h + ' 小时 ' + m + ' 分';
    return m + ' 分 ' + (t % 60) + ' 秒';
  }

  /* ---------- 工作日历 ---------- */
  function WorkCalendar(cfg) {
    this.holidays = {};
    this.makeup = {};
    this.weekdays = {};
    var i;
    for (i = 0; i < cfg.holidays.length; i++) this.holidays[cfg.holidays[i]] = 1;
    for (i = 0; i < cfg.makeup_workdays.length; i++) this.makeup[cfg.makeup_workdays[i]] = 1;
    for (i = 0; i < cfg.work_weekdays.length; i++) this.weekdays[cfg.work_weekdays[i]] = 1;
    this._m = {};
    this._b = {};
  }

  WorkCalendar.prototype.isWorkday = function (d) {
    var k = isoOf(d);
    if (this.holidays[k]) return false;
    if (this.makeup[k]) return true;
    var wd = d.getDay();
    if (wd === 0) wd = 7;
    return !!this.weekdays[wd];
  };

  WorkCalendar.prototype.workdaysInMonth = function (y, m) {
    var key = y + '-' + m;
    if (this._m[key] !== undefined) return this._m[key];
    var n = 0;
    var d = new Date(y, m - 1, 1);
    while (d.getMonth() === m - 1) {
      if (this.isWorkday(d)) n++;
      d.setDate(d.getDate() + 1);
    }
    this._m[key] = n;
    return n;
  };

  WorkCalendar.prototype.workdaysBefore = function (today) {
    var key = isoOf(today);
    if (this._b[key] !== undefined) return this._b[key];
    var n = 0;
    var d = new Date(today.getFullYear(), today.getMonth(), 1);
    while (d < today) {
      if (this.isWorkday(d)) n++;
      d.setDate(d.getDate() + 1);
    }
    this._b[key] = n;
    return n;
  };

  /* ---------- 薪资引擎 ---------- */
  function Engine(cfg) { this.apply(cfg); }

  Engine.prototype.apply = function (cfg) {
    cfg = normalize(cfg);
    this.cfg = cfg;
    this.cal = new WorkCalendar(cfg);
    this.monthly = Math.max(0, toNum(cfg.monthly_salary, 0));

    var s = parseHHMM(cfg.work_start) || { h: 9, mi: 0 };
    var e = parseHHMM(cfg.work_end) || { h: 18, mi: 0 };
    this.startMin = s.h * 60 + s.mi;
    this.endMin = e.h * 60 + e.mi;
    if (this.endMin <= this.startMin) this.endMin = this.startMin + 480;

    var b1 = parseHHMM(cfg.break_start);
    var b2 = parseHHMM(cfg.break_end);
    if (b1 && b2) {
      var bs = b1.h * 60 + b1.mi, be = b2.h * 60 + b2.mi;
      if (be > bs && bs >= this.startMin && be <= this.endMin) {
        this.breakMin = bs;
        this.breakEndMin = be;
        this.breakLen = be - bs;
      } else {
        this.breakMin = this.breakEndMin = this.breakLen = 0;
      }
    } else {
      this.breakMin = this.breakEndMin = this.breakLen = 0;
    }

    this.dayMinutes = this.endMin - this.startMin;
    this.netMinutes = this.dayMinutes - this.breakLen;
    if (this.netMinutes <= 0) this.netMinutes = this.dayMinutes;

    // 发薪日：几号 + 几点。payDay = 0 表示留空，主界面不显示发薪倒计时
    var pt = parseHHMM(cfg.pay_time);
    if (!pt) pt = { h: 17, mi: 0 };
    this.payDay = (cfg.pay_day >= 1 && cfg.pay_day <= 31) ? cfg.pay_day : 0;
    this.payH = pt.h;
    this.payMi = pt.mi;

    var items = [];
    for (var i = 0; i < cfg.items.length; i++) {
      var it = cfg.items[i];
      if (it && it.price > 0) items.push({ name: it.name, price: +it.price });
    }
    items.sort(function (a, b) { return a.price - b.price; });
    this.items = items;
  };

  Object.defineProperty(Engine.prototype, 'netHours', {
    get: function () { return this.netMinutes / 60.0; }
  });

  Engine.prototype.monthIncome = function (y, m) {
    // 补贴 / 特例月的唯一入口，将来只改这里
    return this.monthly;
  };

  Engine.prototype.dailyPay = function (y, m) {
    var n = this.cal.workdaysInMonth(y, m);
    return n ? this.monthIncome(y, m) / n : 0;
  };

  Engine.prototype.hourlyPay = function (y, m) {
    return this.netHours ? this.dailyPay(y, m) / this.netHours : 0;
  };

  Engine.prototype.yearEarned = function (today, monthTotal) {
    var total = 0;
    for (var m = 1; m < today.getMonth() + 1; m++) total += this.monthIncome(today.getFullYear(), m);
    return total + monthTotal;
  };

  /* ---------- 发薪日 ----------
     口径：每月 pay_day 号的 pay_time，碰上非工作日就往前挪到最近的工作日。
     往前挪允许跨月（春节把工资提前到节前最后一个工作日是常规做法），
     最多退 20 天，防节假日表写错时死循环。
     当月没有这一天（比如 31 号遇到 30 天的月份）就按当月最后一天算。 */
  Engine.prototype.paydayAt = function (y, m) {
    var last = new Date(y, m, 0).getDate();          // m 是 1-12
    var day = Math.min(this.payDay, last);
    for (var i = 0; i < 20; i++) {
      var d = new Date(y, m - 1, day - i, this.payH, this.payMi, 0, 0);
      var dayOnly = new Date(d.getFullYear(), d.getMonth(), d.getDate());
      if (this.cal.isWorkday(dayOnly)) return d;
    }
    return new Date(y, m - 1, day, this.payH, this.payMi, 0, 0);
  };

  /* 下一个发薪时刻：本月的过了（或者今天已经到点）就取下个月 */
  Engine.prototype.nextPayday = function (now) {
    var y = now.getFullYear(), m = now.getMonth() + 1;
    var d = this.paydayAt(y, m);
    if (d.getTime() <= now.getTime()) {
      d = m === 12 ? this.paydayAt(y + 1, 1) : this.paydayAt(y, m + 1);
    }
    return d;
  };

  Engine.prototype.snapshot = function (now, demo) {
    var y = now.getFullYear(), mo = now.getMonth(), d = now.getDate();
    var today = new Date(y, mo, d);
    var workday = demo ? true : this.cal.isWorkday(today);

    var monthDays = this.cal.workdaysInMonth(y, mo + 1);
    var daily = monthDays ? this.monthIncome(y, mo + 1) / monthDays : 0;
    var hourly = this.netHours ? daily / this.netHours : 0;
    var perSec = hourly / 3600.0;

    var startDt = new Date(y, mo, d, Math.floor(this.startMin / 60), this.startMin % 60, 0, 0);
    var endDt = new Date(y, mo, d, Math.floor(this.endMin / 60), this.endMin % 60, 0, 0);

    var totalSec = this.netMinutes * 60;
    var spanSec = this.dayMinutes * 60;

    var bsDt = null, beDt = null;
    if (this.breakLen) {
      bsDt = new Date(y, mo, d, Math.floor(this.breakMin / 60), this.breakMin % 60, 0, 0);
      beDt = new Date(y, mo, d, Math.floor(this.breakEndMin / 60), this.breakEndMin % 60, 0, 0);
    }

    var status, worked;
    if (!workday) {
      status = '休息';
      worked = 0;
    } else {
      var raw = (now.getTime() - startDt.getTime()) / 1000;
      raw = Math.max(0, Math.min(raw, spanSec));
      if (this.breakLen) {
        var passed = (now.getTime() - bsDt.getTime()) / 1000;
        passed = Math.max(0, Math.min(passed, this.breakLen * 60));
        worked = Math.max(0, raw - passed);
      } else {
        worked = raw;
      }
      if (now.getTime() < startDt.getTime()) status = '未开工';
      else if (now.getTime() >= endDt.getTime()) status = '已下班';
      else if (this.breakLen && now.getTime() >= bsDt.getTime() && now.getTime() < beDt.getTime()) status = '小憩';
      else status = '上班中';
    }

    var remaining = Math.max(0, totalSec - worked);
    /* 距下班的"时钟口径"剩余：此刻到下班时刻的真实时长（含午休）。
       remaining 是净工时口径（午休不计入），午休期间一动不动——
       那是"还要干多少活"的正确答案，但拿去当"距下班倒计时"就是 bug。 */
    var clockLeft = Math.max(0, (endDt.getTime() - now.getTime()) / 1000);
    var progress = totalSec ? worked / totalSec : 0;
    var earned = hourly * worked / 3600.0;
    var doneDays = this.cal.workdaysBefore(today);
    var monthTotal = daily * doneDays + earned;
    var speed = status === '上班中' ? perSec : 0;

    var msg = this.buildMessage({
      status: status, now: now, startDt: startDt, remaining: remaining,
      perSec: perSec, hourly: hourly, earned: earned
    });

    // 发薪日跟着"现在"走：演示模式的假时钟也会算出对应的下一个发薪时刻。
    // 用户把发薪日留空时 payDay = 0，这里就是 null —— 界面那行整条不显示。
    var payday = this.payDay ? this.nextPayday(now) : null;

    /* 时间轴进度：从上班到现在在整段工时里走过的比例（含午休）。
       进度条按它画，午休才能在轴上有真实长度（1 小时就是 1/9）。
       跟上面的 progress（净工时完成度）是两个口径，别混：
       progress 回答"干完多少活"，spanProgress 回答"今天过到哪"。 */
    var elapsedMin = 0;
    if (workday) {
      elapsedMin = (now.getTime() - startDt.getTime()) / 60000;
      elapsedMin = Math.max(0, Math.min(elapsedMin, this.dayMinutes));
    }
    var spanProgress = this.dayMinutes ? elapsedMin / this.dayMinutes : 0;

    return {
      now: now, today: today, status: status, isWorkday: workday,
      worked: worked, remaining: remaining, clockLeft: clockLeft, totalSec: totalSec,
      progress: progress, spanProgress: spanProgress,
      earned: earned, monthTotal: monthTotal,
      yearEarned: this.yearEarned(today, monthTotal),
      dailyPay: daily, hourly: hourly, perSec: perSec, speed: speed,
      monthDays: monthDays, doneDays: doneDays, msg: msg,
      payday: payday,
      paydayLeft: payday ? Math.max(0, (payday.getTime() - now.getTime()) / 1000) : 0
    };
  };

  /* ---------- 鼓励语（结构化，方便排版） ---------- */
  Engine.prototype.buildMessage = function (c) {
    var eps = 1e-6;
    var items = this.items;
    var earned = c.earned;
    var reach = earned + c.remaining * c.perSec;
    var self = this;

    function bought() {
      var r = null;
      for (var i = 0; i < items.length; i++) if (items[i].price <= earned + eps) r = items[i];
      return r;
    }
    function next() {
      for (var i = 0; i < items.length; i++) if (items[i].price > earned + eps) return items[i];
      return null;
    }

    if (c.status === '未开工') {
      var left = Math.max(0, (c.startDt.getTime() - c.now.getTime()) / 1000);
      var best = null;
      for (var i = 0; i < items.length; i++) if (items[i].price <= reach + eps) best = items[i];
      return { kind: 'distance', text: '距离上班还有 ' + fmtDur(left), best: best, left: left };
    }
    if (c.status === '小憩') {
      return { kind: 'rest', text: '小憩中，钱和你一起休息', got: bought() };
    }
    if (c.status === '已下班') {
      return { kind: 'off', text: '今天已收工', got: bought(), earned: earned };
    }
    if (c.status === '休息') {
      return { kind: 'holiday', text: '今天是休息日，不赚钱也是应该的' };
    }
    if (!items.length || c.hourly <= 0) {
      return { kind: 'plain', text: '今天也在赚钱，稳住' };
    }

    var got = bought(), nxt = next();

    if (nxt === null) {
      return { kind: 'done', got: got, remaining: c.remaining * c.perSec };
    }

    var need = Math.max(0, (nxt.price - earned) / c.hourly * 3600);
    if (got !== null) {
      return { kind: 'item', got: got, nxt: nxt, need: need };
    }
    if (nxt.price <= reach + eps) {
      return { kind: 'item', got: null, nxt: nxt, need: need };
    }
    return { kind: 'item', got: null, nxt: nxt, need: need, gap: nxt.price - reach, reach: reach };
  };

  return {
    DEFAULT_CFG: DEFAULT_CFG,
    STORE_KEY: STORE_KEY,
    THEME_LIST: THEME_LIST,
    normalize: normalize,
    loadCfg: loadCfg,
    saveCfg: saveCfg,
    hasSaved: hasSaved,
    markReady: markReady,
    resetSaved: resetSaved,
    defaults: function () { return JSON.parse(JSON.stringify(DEFAULT_CFG)); },
    Engine: Engine,
    WorkCalendar: WorkCalendar,
    fmtMoney: fmtMoney,
    fmtNum: fmtNum,
    fmtHMSms: fmtHMSms,
    fmtDur: fmtDur,
    isoOf: isoOf,
    parseHHMM: parseHHMM
  };
})();
/* ==ENGINE-END== */

/* 只在 Node 下导出，方便直接跑回归用例（tests/engine.test.js）：
   node -e "var G=require('./src/engine.js')"。浏览器里有 window，这一段直接跳过。 */
if (typeof window === 'undefined' && typeof module !== 'undefined' && module.exports) {
  module.exports = Guliqi;
}
