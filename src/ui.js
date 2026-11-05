(function () {
  'use strict';

  var G = window.Guliqi;
  var $ = function (id) { return document.getElementById(id); };

  var refs = {
    badge: $('badge'), date: $('date'), clock: $('clock'), weekday: $('weekday'),
    earned: $('earned'), cur: $('cur'), speed: $('speed'), phaseNote: $('phaseNote'),
    msg: $('msg'), msgBody: $('msgBody'),
    duoWorked: $('duoWorked'), duoLeft: $('duoLeft'),
    duoIn: $('duoIn'), duoOut: $('duoOut'),
    pct: $('pct'), barFill: $('barFill'), barBreak: $('barBreak'),
    monthTotal: $('monthTotal'), yearEarned: $('yearEarned'),
    hourly: $('hourly'), dailyPay: $('dailyPay'),
    dayNo: $('dayNo'), dayTotal: $('dayTotal'), days: $('days'),
    paydayRow: $('paydayRow'),
    paydayLeft: $('paydayLeft'), paydayWhen: $('paydayWhen'),
    hideTxt: $('hideTxt'),
    tag: document.querySelector('.tag')
  };

  var cfg = G.loadCfg();
  var engine = new G.Engine(cfg);
  var cache = {};
  var calKey = '';
  var titleTick = 0;

  /* ---------- 主题 ----------
     三种模式：system（跟随系统）/ light / dark。
     head 里那段内联脚本已经在首帧之前画过一次，这里只负责之后的变化
     （用户改设置、系统明暗切换时）。 */
  var themeMQ = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var draftTheme = cfg.theme;      // 面板里点中但还没保存的值

  function sysIsDark() {
    return !!(themeMQ && themeMQ.matches);
  }

  function applyTheme(mode) {
    var m = (mode === 'light' || mode === 'dark') ? mode : 'system';
    var dark = (m === 'dark') || (m === 'system' && sysIsDark());
    var root = document.documentElement;
    root.setAttribute('data-theme', dark ? 'dark' : 'light');
    // 手机/独立窗口的标题栏、任务栏跳转列表都读这个
    var meta = document.querySelector('meta[name=theme-color]');
    if (meta) meta.setAttribute('content', dark ? '#07090d' : '#f5f6f8');
    root.style.colorScheme = dark ? 'dark' : 'light';
    paintThemeBtn(dark);
  }

  // 顶栏那个图标的提示跟着实际明暗走（图标本身靠 CSS 的 [data-theme] 切）
  function paintThemeBtn(dark) {
    var b = $('btnTheme');
    if (!b) return;
    var tip = dark ? '切换到浅色主题' : '切换到深色主题';
    b.setAttribute('title', tip);
    b.setAttribute('aria-label', tip);
  }

  function paintThemeSeg() {
    var box = $('fTheme');
    if (!box) return;
    var btns = box.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      var on = btns[i].getAttribute('data-theme-opt') === draftTheme;
      btns[i].classList.toggle('on', on);
      btns[i].setAttribute('aria-pressed', on ? 'true' : 'false');
    }
  }

  // 系统明暗变化：只有"跟随系统"时才跟着动；用户明确选了浅/深就保持不变
  function onSysThemeChange() {
    if (cfg.theme === 'system') applyTheme('system');
  }
  if (themeMQ) {
    if (themeMQ.addEventListener) themeMQ.addEventListener('change', onSysThemeChange);
    else if (themeMQ.addListener) themeMQ.addListener(onSysThemeChange);
  }

  applyTheme(cfg.theme);

  // 演示时钟：把"现在"整体挪一个固定偏移。偏移不变 = 时钟照样一秒一秒往前走，
  // 不是冻在某一刻，这样金额和进度都还是活的。
  function nowAt() {
    var off = (cfg.demo && cfg.demo_offset) ? cfg.demo_offset : 0;
    return off ? new Date(Date.now() + off) : new Date();
  }

  function setText(key, val) {
    if (cache[key] === val) return;
    cache[key] = val;
    var node = refs[key];
    if (node) node.textContent = val;
  }

  function setHTML(key, val) {
    if (cache[key] === val) return;
    cache[key] = val;
    if (refs.msgBody) refs.msgBody.innerHTML = val;
  }

  function mask(v) { return cfg.display.hide_money ? '****' : v; }

  function money(v) { return cfg.display.hide_money ? '****' : G.fmtMoney(v); }

  var WEEK_CN = '日一二三四五六';

  /* ---------- 发薪日文案 ----------
     中文单位直接读：「3天5小时12分8秒」，不再用冒号堆成一串。
     天为 0 就不写"0 天"，小时同理，最短退到「12分8秒」。
     精度到秒：主循环每帧都算，秒位自然跟着走。 */
  function fmtPayLeft(sec) {
    sec = Math.max(0, sec || 0);
    var d = Math.floor(sec / 86400);
    var h = Math.floor((sec % 86400) / 3600);
    var mi = Math.floor((sec % 3600) / 60);
    var s = Math.floor(sec % 60);
    var out = '';
    if (d > 0) out += d + '天';
    if (d > 0 || h > 0) out += h + '小时';
    if (d > 0 || h > 0 || mi > 0) out += mi + '分';
    return out + s + '秒';
  }

  function fmtPayWhen(d, today) {
    var pad = function (n) { return String(n).padStart(2, '0'); };
    var hm = pad(d.getHours()) + ':' + pad(d.getMinutes());
    var one = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    var diff = Math.round((one.getTime() - today.getTime()) / 86400000);
    if (diff === 0) return '今天 ' + hm;
    if (diff === 1) return '明天 ' + hm;
    return (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + hm;
  }

  /* ---------- 进度轴上的午休 ----------
     轴用"当天时间"当刻度（09:00 → 18:00），午休段就按它的真实时长占位：
     午休 1 小时、一天跨度 9 小时，它就占 1/9，跟眼睛看到的时长一致。
     填充也跟着这条轴走（spanProgress，含午休），午休那一段被不透明的斜纹盖住，
     所以视觉上就是"绿条停在午休左边，午休不赚钱，13:00 再从右边接着走"。
     右边那个百分比仍是净工时完成度（跟"已工作 / 总工作"对得上），两者口径不同。 */
  function paintBarBreak() {
    var box = refs.barBreak;
    if (!box) return;
    var e = engine;
    var on = !!(e && e.breakLen > 0 && e.netMinutes > 0 && e.dayMinutes > 0);
    if (cache.breakOn !== on) {
      cache.breakOn = on;
      box.style.display = on ? '' : 'none';
    }
    if (!on) return;
    var left = (e.breakMin - e.startMin) / e.dayMinutes;
    var wide = e.breakLen / e.dayMinutes;
    if (cache.breakL !== left || cache.breakW !== wide) {
      cache.breakL = left;
      cache.breakW = wide;
      box.style.left = (left * 100).toFixed(3) + '%';
      box.style.width = (wide * 100).toFixed(3) + '%';
      box.title = '午休 ' + hhmmOf(e.breakMin) + ' – ' + hhmmOf(e.breakEndMin);
    }
  }

  var STATUS_KEY = {
    '上班中': 'work', '小憩': 'rest', '已下班': 'off', '未开工': 'idle', '休息': 'holiday'
  };

  /* ---------- 鼓励语渲染 ---------- */
  function renderMsg(m) {
    var esc = function (s) {
      return String(s).replace(/[&<>]/g, function (c) {
        return c === '&' ? '&amp;' : c === '<' ? '&lt;' : '&gt;';
      });
    };
    switch (m.kind) {
      case 'item':
        if (m.gap !== undefined) {
          return '今天还能赚 <em>' + money(m.reach) + '</em>，离' + esc(m.nxt.name) + '还差 <em>' + money(m.gap) + '</em>';
        }
        if (m.got) {
          return '已赚回 <em>' + esc(m.got.name) + '</em>' +
                 '<span class="to">·</span><span class="arrow">再过</span> <em>' + G.fmtDur(m.need) + '</em>，' +
                 esc(m.nxt.name) + '就到手';
        }
        return '<span class="arrow">再过</span> <em>' + G.fmtDur(m.need) + '</em>，' + esc(m.nxt.name) + '就到手';
      case 'done':
        return '今天已经赚回 <em>' + esc(m.got ? m.got.name : '') + '</em>，收工前还能再赚 <em>' + money(m.remaining) + '</em>';
      case 'distance':
        return '距离上班还有 <em>' + G.fmtDur(m.left) + '</em>' +
               (m.best ? '，今天满勤能赚回 <em>' + esc(m.best.name) + '</em>' : '，开工那一刻计时就开始跑');
      case 'rest':
        return '小憩中，钱和你一起休息' + (m.got ? '，已赚回 <em>' + esc(m.got.name) + '</em>' : '');
      case 'off':
        return '今天已收工' + (m.got ? '，赚回 <em>' + esc(m.got.name) + '</em>' : '') +
               '，<em>' + money(m.earned) + '</em> 入库。明天继续';
      case 'holiday':
        return '今天是休息日，不赚钱也是应该的';
      default:
        return '今天也在赚钱，稳住';
    }
  }

  /* ---------- 日历 ----------
     可以翻月；点任意一天能写一句备注，备注存在 SQLite（Python 侧 store.py）。
     没有桌面桥时（浏览器直开）备注只留在内存里，界面上照常能写，只是关掉就没了。 */
  var view = null;          // {y, m}，m 从 0 开始；null = 跟随今天所在月份
  var notes = {};           // 当前显示月份的备注 {日期: 文本}
  var notesKey = '';        // 已拉过哪个月，避免每帧都问一次

  function monthKey(y, m) { return y + '-' + (m < 9 ? '0' : '') + (m + 1); }

  function viewOf(date) { return { y: date.getFullYear(), m: date.getMonth() }; }

  function sameView(a, b) { return !!a && !!b && a.y === b.y && a.m === b.m; }

  function loadNotes() {
    var key = monthKey(view.y, view.m);
    if (key === notesKey) return;
    notesKey = key;
    notes = {};
    var p = desk.call('get_notes', key);
    if (p && typeof p.then === 'function') {
      p.then(function (res) {
        notes = (res && typeof res === 'object') ? res : {};
        calKey = '';      // 数据回来了，下一帧重画（补上小圆点）
      }, function () {});
    }
  }

  function renderCalendar(snap) {
    if (!view) view = viewOf(snap.today);
    var t = snap.today;
    var isCur = sameView(view, viewOf(t));
    var key = view.y + '-' + view.m + '|' + G.isoOf(t) + '|' + snap.status + '|' + Object.keys(notes).length;
    if (key === calKey) return;
    calKey = key;
    loadNotes();

    $('calTitle').innerHTML = '<b>' + view.y + '</b> 年 <b>' + (view.m + 1) + '</b> 月';
    $('calToday').style.display = isCur ? 'none' : '';

    var first = new Date(view.y, view.m, 1);
    var lead = (first.getDay() + 6) % 7;          // 周一为一周之始
    var last = new Date(view.y, view.m + 1, 0).getDate();
    var cal = engine.cal;
    var tIso = G.isoOf(t);
    var html = '';

    for (var i = 0; i < lead; i++) html += '<div class="day pad"></div>';

    for (var d = 1; d <= last; d++) {
      var dt = new Date(view.y, view.m, d);
      var iso = G.isoOf(dt);
      var cls = 'day';
      if (iso === tIso) cls += ' today';
      else if (cal.isWorkday(dt)) cls += dt.getTime() < t.getTime() ? ' done' : ' todo';
      else if (cal.holidays[iso]) cls += ' holiday';
      else cls += ' weekend';
      if (notes[iso]) cls += ' hasnote';
      // 小字：节日名优先（春节/中秋/除夕…），否则农历日，初一显示月名
      var lab = (typeof Lunar !== 'undefined') && Lunar.dayLabel(dt);
      var sub = lab ? lab.text : '';
      if (lab && lab.festival) cls += ' fest';
      html += '<div class="' + cls + '" data-d="' + iso + '"'
        + (notes[iso] ? ' title="' + escAttr(notes[iso]) + '"' : '') + '>'
        + '<b>' + d + '</b>' + (sub ? '<i>' + sub + '</i>' : '')
        + '</div>';
    }
    refs.days.innerHTML = html;
  }

  function escAttr(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return c === '&' ? '&amp;' : c === '<' ? '&lt;' : c === '>' ? '&gt;' : '&quot;';
    });
  }

  function redrawCalendar() {
    calKey = '';
    renderCalendar(engine.snapshot(nowAt(), cfg.demo));
  }

  function shiftMonth(delta) {
    if (!view) view = viewOf(engine.snapshot(nowAt(), cfg.demo).today);
    var m = view.m + delta, y = view.y;
    if (m < 0) { m = 11; y--; } else if (m > 11) { m = 0; y++; }
    view = { y: y, m: m };
    notes = {};
    notesKey = '';
    redrawCalendar();
  }

  $('calPrev').addEventListener('click', function () { shiftMonth(-1); });
  $('calNext').addEventListener('click', function () { shiftMonth(1); });
  $('calToday').addEventListener('click', function () {
    view = null;
    notes = {};
    notesKey = '';
    redrawCalendar();
  });

  /* ---------- 日期备注 ---------- */
  var noteDate = '';

  /* 有浮层（设置面板 / 备注弹窗）时锁住背后的页面。
     不然滚轮在遮罩上继续滚，背后那页会跟着滑走，关掉浮层后位置全变 —— 
     看上去就像"内容错位"。按当前有几个浮层统一算一次，先开后关都不会漏。 */
  function syncLock() {
    var on = sheet.classList.contains('open') || $('notePop').classList.contains('open');
    document.documentElement.classList.toggle('lock', on);
  }

  function openNote(iso) {
    noteDate = iso;
    var body = notes[iso] || '';
    var p = iso.split('-');
    $('noteTitle').textContent = (+p[1]) + ' 月 ' + (+p[2]) + ' 日';
    $('noteBody').value = body;
    $('noteDel').style.display = body ? '' : 'none';
    paintNoteCnt();
    $('notePop').classList.add('open');
    syncLock();
    setTimeout(function () { try { $('noteBody').focus(); } catch (e) {} }, 60);
  }

  function closeNote() {
    $('notePop').classList.remove('open');
    syncLock();
  }

  function paintNoteCnt() {
    var n = $('noteBody').value.length;
    $('noteCnt').textContent = n + ' / 100';
    $('noteCnt').classList.toggle('warn', n >= 95);
  }

  function commitNote(text) {
    var body = String(text || '').slice(0, 100);
    if (body) notes[noteDate] = body; else delete notes[noteDate];
    closeNote();
    redrawCalendar();          // 先把界面改掉，写库在后台完成
    if (!desk.ready()) return;
    desk.send('set_note', { date: noteDate, body: body });
  }

  refs.days.addEventListener('click', function (e) {
    var cell = e.target && e.target.closest ? e.target.closest('.day') : null;
    if (!cell) return;
    var iso = cell.getAttribute('data-d');
    if (iso) openNote(iso);
  });

  $('noteBody').addEventListener('input', paintNoteCnt);
  $('noteCancel').addEventListener('click', closeNote);
  $('noteMask').addEventListener('click', closeNote);
  $('noteDel').addEventListener('click', function () { commitNote(''); });
  $('noteSave').addEventListener('click', function () { commitNote($('noteBody').value); });
  $('noteBody').addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { e.stopPropagation(); closeNote(); }
    // Ctrl/⌘ + Enter 直接存，长备注不用去点按钮
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); commitNote($('noteBody').value); }
  });

  /* ---------- 主渲染 ---------- */
  function frame(now) {
    var snap = engine.snapshot(now, cfg.demo);
    trackPhase(snap);            // 跨过午休/下班时点就发一条系统通知

    // 演示生效时把标签和时钟标成金色，免得把假时间当成真的
    var demoOn = !!(cfg.demo && cfg.demo_offset);
    if (cache.demoOn !== demoOn) {
      cache.demoOn = demoOn;
      document.body.classList.toggle('demo-on', demoOn);
      if (refs.tag) refs.tag.textContent = demoOn ? 'DEMO · 假时钟' : 'EARN · LIVE';
    }

    // 星期和时间是这张卡的头，单独一行钉在最上面
    setText('weekday', '星期' + WEEK_CN[snap.today.getDay()]);
    setText('date', (snap.today.getMonth() + 1) + '月' + snap.today.getDate() + '日');

    var hh = String(now.getHours()).padStart(2, '0');
    var mm = String(now.getMinutes()).padStart(2, '0');
    var ss = String(now.getSeconds()).padStart(2, '0');
    var ms = String(now.getMilliseconds()).padStart(3, '0');
    setText('clock', hh + ':' + mm + ':' + ss + '.' + ms);

    var sk = STATUS_KEY[snap.status] || 'idle';
    if (cache.status !== snap.status) {
      cache.status = snap.status;
      refs.badge.setAttribute('data-s', sk);
      refs.badge.textContent = snap.status;
    }

    // 金额
    var hide = cfg.display.hide_money;
    var earnedTxt = hide ? '****' : G.fmtNum(snap.earned);
    setText('earned', earnedTxt);
    if (cache.masked !== hide) {
      cache.masked = hide;
      refs.earned.classList.toggle('masked', hide);
      refs.cur.style.visibility = hide ? 'hidden' : 'visible';
    }

    setText('speed', hide ? '****' : snap.speed.toFixed(4));
    setText('phaseNote', '今天共 ' + engine.netHours.toFixed(2) + ' 小时计薪');
    setText('duoWorked', G.fmtHMSms(snap.worked));
    // 距下班用时钟口径（含午休，任何时段都在走）；休息日没有"下班时刻"，退回净工时口径
    setText('duoLeft', G.fmtHMSms(snap.isWorkday ? snap.clockLeft : snap.remaining));

    // 鼓励语
    var kindKey = snap.msg.kind === 'item' && snap.msg.gap !== undefined ? 'item' : snap.msg.kind;
    if (cache.msgKind !== snap.msg.kind) {
      cache.msgKind = snap.msg.kind;
      refs.msg.setAttribute('data-k', kindKey);
    }
    setHTML('msg', renderMsg(snap.msg));

    // 进度：数字是净工时完成度，条形长度是"今天过到哪"（含午休，见 spanProgress）
    setText('pct', (snap.progress * 100).toFixed(1) + '%');
    var p = Math.max(0, Math.min(1, snap.spanProgress));
    if (cache.barP !== p) {
      cache.barP = p;
      refs.barFill.style.width = (p * 100).toFixed(3) + '%';
    }
    paintBarBreak();

    // 统计
    setText('monthTotal', money(snap.monthTotal));
    setText('yearEarned', money(snap.yearEarned));
    setText('hourly', hide ? '****' : '￥' + G.fmtNum(snap.hourly));
    setText('dailyPay', money(snap.dailyPay));
    ['monthTotal', 'yearEarned', 'hourly', 'dailyPay'].forEach(function (k) {
      if (refs[k]) refs[k].classList.toggle('masked', hide);
    });

    // 发薪日倒计时：用户留空就整行收起，不留一条空横条
    var payOn = !!snap.payday;
    if (cache.payOn !== payOn) {
      cache.payOn = payOn;
      refs.paydayRow.style.display = payOn ? '' : 'none';
    }
    if (payOn) {
      setText('paydayLeft', fmtPayLeft(snap.paydayLeft));
      setText('paydayWhen', fmtPayWhen(snap.payday, snap.today));
    }

    // 日历
    setText('dayNo', String(snap.doneDays + (snap.isWorkday ? 1 : 0)));
    setText('dayTotal', String(snap.monthDays));
    renderCalendar(snap);

    // 标题栏（藏钱时一并打码）
    titleTick += 1;
    if (titleTick >= 30) {
      titleTick = 0;
      document.title = hide ? '上班鼓励器 · ****' : '上班鼓励器 · ' + G.fmtMoney(snap.earned);
    }
  }

  var raf = null;
  var lastFrame = 0;
  var running = false;      // 首次设置没完成前不跑主循环

  function loop() {
    lastFrame = Date.now();
    frame(nowAt());
    raf = requestAnimationFrame(loop);
  }

  // 兜底：极少数环境（省电模式 / 部分无头浏览器）rAF 不推进，靠定时器保底刷新
  setInterval(function () {
    if (!running) return;
    if (Date.now() - lastFrame > 250) { lastFrame = Date.now(); frame(nowAt()); }
  }, 120);

  // 两个大数下面那行小字：几点上班、几点下班
  function paintDuoNotes() {
    setText('duoIn', cfg.work_start + ' 上班');
    setText('duoOut', cfg.work_end + ' 下班');
  }

  /* ---------- 窗口高度自适应 ----------
     初始窗口 900 高是拍脑袋给的，内容经常用不满，底栏下面空一大块。
     启动后把页面实际高度报给桌面层（fit_window），由它把窗口收到刚好。
     量两次：渲染完一次，字体加载/首帧稳定后再补一次；一个会话最多两次，
     之后窗口归用户管，手动拉大拉小都不打扰。

     用户自己拖过窗口（桌面层记住了尺寸）就一次都不收——他要多大就多大。 */
  var winSaved = false;      // 桌面层是否存着上次的窗口尺寸
  var fitCount = 0;
  function fitWindow() {
    // 次数上限只在 fitWindowSoon 里卡：这里再判 >= 2 会把第二次补量直接吞掉
    if (!desk.ready() || winSaved) return;
    desk.send('fit_window', Math.ceil(document.documentElement.scrollHeight));
  }
  function fitWindowSoon(delay) {
    if (winSaved || fitCount >= 2) return;
    fitCount++;
    setTimeout(fitWindow, delay);
  }

  function start() {
    if (raf !== null) cancelAnimationFrame(raf);
    cache = {};
    calKey = '';
    lastPhase = '';        // 重算一开始（含刚改完作息）就把当前时点当成起点，不补发提醒
    engine = new G.Engine(cfg);
    paintDuoNotes();
    running = true;
    loop();
    fitWindowSoon(350);    // 渲染一帧后量高度，收一次窗口
    setTimeout(function () { fitWindowSoon(0); }, 1200);  // 字体/布局稳定后再补一次
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      if (raf !== null) { cancelAnimationFrame(raf); raf = null; }
    } else if (raf === null && running) {
      loop();
    }
  });

  /* ---------- 隐藏金额 ---------- */
  function toggleHide() {
    cfg.display.hide_money = !cfg.display.hide_money;
    G.saveCfg(cfg);                     // 本地缓存，下次启动第一帧就不闪
    desk.send('save_cfg', cfg);         // 权威存储：SQLite
    cache = {};
    titleTick = 29;
    refs.hideTxt.textContent = cfg.display.hide_money ? '显示金额' : '隐藏金额';
    document.getElementById('eyeIcon').innerHTML = cfg.display.hide_money
      ? '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line>'
      : '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"></path><circle cx="12" cy="12" r="3"></circle>';
  }

  $('btnHide').addEventListener('click', toggleHide);

  /* ---------- 设置面板 ---------- */
  var sheet = $('sheet');
  var panel = $('panel');
  var weekBtns = Array.prototype.slice.call(document.querySelectorAll('#fWeek button'));
  var draftWeek = cfg.work_weekdays.slice();
  var firstRun = false;          // true = 首次进入，必须先填完才能进主界面

  /* ---------- 标签页 ----------
     面板内容已经长到一屏放不下，改成按主题分页；每页各自滚动，标题和标签栏固定。 */
  var TABS = ['work', 'cal', 'items', 'look', 'desk', 'about'];
  var curTab = 'work';

  /* 「桌面」标签只在桌面版（Python 桥就绪）显示：
     纯 HTML 直开时开机启动/查更新/到点提醒全是空话，页面是空白的，直接藏掉。 */
  function paintDeskTab() {
    var on = desk.ready();
    var tabBtn = $('panelTabs').querySelector('button[data-pane="desk"]');
    var pane = panel.querySelector('.tab-pane[data-pane="desk"]');
    if (tabBtn) tabBtn.style.display = on ? '' : 'none';
    if (pane) pane.style.display = on ? '' : 'none';
    if (!on && curTab === 'desk') { curTab = 'work'; }
  }

  function paintTabs() {
    var btns = $('panelTabs').querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      var on = btns[i].getAttribute('data-pane') === curTab;
      btns[i].classList.toggle('on', on);
      btns[i].setAttribute('aria-selected', on ? 'true' : 'false');
    }
    var panes = panel.querySelectorAll('.tab-pane');
    for (var j = 0; j < panes.length; j++) {
      panes[j].classList.toggle('active', panes[j].getAttribute('data-pane') === curTab);
    }
  }

  function switchTab(name) {
    if (TABS.indexOf(name) < 0) return;
    curTab = name;
    paintTabs();
    var pb = panel.querySelector('.panel-body');
    if (pb) pb.scrollTop = 0;
  }

  $('panelTabs').addEventListener('click', function (e) {
    var b = e.target && e.target.closest ? e.target.closest('button') : null;
    if (b) switchTab(b.getAttribute('data-pane'));
  });

  /* ---------- 面板高度固定 ----------
     六页长短不一，以前切标签面板会整体变高变矮，看着像在跳。现在量「工时」
     那一页的自然高度，把它写成内容区的固定高度：其余页撑满同一块，切页零跳动。
     窄窗口下工时页本来就装不下，那块高度会被面板的 max-height 压小，
     内容在内部滚动（滚动条不画）。窗口大小变了要重测——不在工时页时克隆一份
     到画布外量，不会闪。 */
  function panelBodyHeight() {
    var body = panel.querySelector('.panel-body');
    var work = panel.querySelector('.tab-pane[data-pane="work"]');
    if (!body || !work) return 0;
    var cs = getComputedStyle(body);
    var padH = parseFloat(cs.paddingLeft || 0) + parseFloat(cs.paddingRight || 0);
    var padV = parseFloat(cs.paddingTop || 0) + parseFloat(cs.paddingBottom || 0);
    var probe = work.cloneNode(true);
    probe.removeAttribute('id');
    var ids = probe.querySelectorAll('[id]');
    for (var i = 0; i < ids.length; i++) ids[i].removeAttribute('id');
    // overflow:hidden 让探针自己成为 BFC：最后一项的下边距也算进高度，
    // 否则量出来会比真实内容矮十来像素，滚动条边界刚好卡在最后一行上。
    // height:auto 抵掉克隆来的 height:100%——不然探针会被面板自身高度拉伸，
    // 量出个"跟面板一样高"，越量越大，最后永远顶到上限。
    probe.style.cssText = 'display:block;position:absolute;left:-9999px;top:0;visibility:hidden;'
      + 'overflow:hidden;height:auto;width:' + Math.max(120, body.clientWidth - padH) + 'px';
    body.appendChild(probe);
    var h = probe.offsetHeight;
    body.removeChild(probe);
    return h + padV;
  }

  function fitPanelBody() {
    var body = panel.querySelector('.panel-body');
    if (!body) return;
    // 首次引导只有一页、也没有标签栏，让它按内容自然高就行
    if (panel.classList.contains('setup')) { body.style.height = ''; return; }
    var head = panel.querySelector('.panel-head');
    var tabs = panel.querySelector('.panel-tabs');
    var acts = panel.querySelector('.panel-actions');
    var ratio = window.matchMedia('(min-width:720px)').matches ? 0.86 : 0.88;
    var chrome = (head ? head.offsetHeight : 0) + (tabs ? tabs.offsetHeight : 0)
               + (acts ? acts.offsetHeight : 0);
    var cap = Math.floor(window.innerHeight * ratio) - chrome - 2;   // 2 = 面板上下边框
    if (cap < 160) cap = 160;
    var need = panelBodyHeight() || cap;
    body.style.height = Math.min(need, cap) + 'px';
  }

  var panelFitTimer = null;
  window.addEventListener('resize', function () {
    if (!sheet.classList.contains('open')) return;
    if (panelFitTimer) clearTimeout(panelFitTimer);
    panelFitTimer = setTimeout(fitPanelBody, 120);
  });

  function paintWeek() {
    weekBtns.forEach(function (b) {
      var n = parseInt(b.getAttribute('data-w'), 10);
      b.classList.toggle('on', draftWeek.indexOf(n) >= 0);
    });
  }

  function clearErrors() {
    ['salaryErr', 'timeErr', 'breakErr'].forEach(function (id) {
      var el = $(id);
      el.textContent = '';
      el.classList.remove('on');
    });
    $('fSalary').style.borderColor = '';
  }

  function showErr(id, msg, field) {
    var el = $(id);
    el.textContent = msg;
    el.classList.add('on');
    if (field) field.style.borderColor = 'rgba(255,139,139,.55)';
  }

  /* ---------- 演示时间 ---------- */
  function hhmmOf(min) {
    min = ((min % 1440) + 1440) % 1440;
    return String(Math.floor(min / 60)).padStart(2, '0') + ':' + String(min % 60).padStart(2, '0');
  }

  function minOfDate(d) { return d.getHours() * 60 + d.getMinutes(); }

  // 只按分钟对齐、秒和毫秒沿用真实的，免得秒针突然跳回 00
  function offsetOfHHMM(hhmm) {
    var t = G.parseHHMM(hhmm);
    if (!t) return 0;
    return ((t.h * 60 + t.mi) - minOfDate(new Date())) * 60000;
  }

  // 快捷时段跟着用户自己的作息算，不写死时间
  function chipDefs() {
    var s = toMin(cfg.work_start), e = toMin(cfg.work_end);
    var list = [];
    if (s !== null) list.push({ min: s + 5, label: '刚开工' });
    if (cfg.break_start && cfg.break_end) {
      var bs = toMin(cfg.break_start), be = toMin(cfg.break_end);
      if (bs !== null && be !== null && be > bs) list.push({ min: Math.round((bs + be) / 2), label: '午休中' });
    }
    if (e !== null) {
      if (s === null || e - 10 > s) list.push({ min: e - 10, label: '临下班' });
      list.push({ min: e + 30, label: '已下班' });
    }
    return list;
  }

  function renderDemoChips() {
    var box = $('demoChips');
    if (!box) return;
    box.innerHTML = chipDefs().map(function (c) {
      var t = hhmmOf(c.min);
      return '<button type="button" data-t="' + t + '">' + t + ' ' + c.label + '</button>';
    }).join('');
    paintChips();
  }

  function paintChips() {
    var v = $('fDemoTime').value;
    var btns = $('demoChips').querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle('on', btns[i].getAttribute('data-t') === v);
    }
  }

  function syncDemoUI(autoFill) {
    var on = $('fDemo').checked;
    $('demoTimeBox').style.display = on ? '' : 'none';
    if (!on) return;
    if (autoFill && !$('fDemoTime').value) {
      // 刚勾上还没设时间：默认给「下班前一小时」，这时进度和金额都肉眼可见
      var s = toMin(cfg.work_start), e = toMin(cfg.work_end);
      var d = (e === null) ? 17 * 60 : e - 60;
      if (s !== null && d < s + 30) d = s + 30;
      $('fDemoTime').value = hhmmOf(d);
      paintChips();
    }
  }

  function openSheet(isFirst) {
    firstRun = !!isFirst;
    panel.classList.toggle('setup', firstRun);
    document.body.classList.toggle('firstrun', firstRun);
    clearErrors();

    $('panelTitle').textContent = firstRun ? '先花 20 秒设置一下' : '设置';
    $('panelSub').textContent = firstRun
      ? '填完就能看到今天赚了多少。数据只存在这台电脑上，不上传任何地方。'
      : '改完点保存立即生效，只存在这台电脑的数据库里。';
    $('btnSave').textContent = firstRun ? '开始计算' : '保存';
    $('setupVer').textContent = $('verNum').textContent;   // 引导页右上的版本号，跟底栏同源
    $('salaryReq').style.display = firstRun ? 'inline-block' : 'none';

    if (firstRun) {
      // 首次进入：不带任何既有薪资，时间给通用预填值，等你自己确认
      $('fSalary').value = '';
      $('fStart').value = '09:00';
      $('fEnd').value = '18:00';
      $('fBreakS').value = '12:00';
      $('fBreakE').value = '13:00';
      $('fPayDay').value = G.DEFAULT_CFG.pay_day;
      $('fPayTime').value = G.DEFAULT_CFG.pay_time;
      draftWeek = [1, 2, 3, 4, 5];
    } else {
      $('fSalary').value = cfg.monthly_salary;
      $('fStart').value = cfg.work_start;
      $('fEnd').value = cfg.work_end;
      $('fBreakS').value = cfg.break_start;
      $('fBreakE').value = cfg.break_end;
      $('fPayDay').value = cfg.pay_day ? cfg.pay_day : '';
      $('fPayTime').value = cfg.pay_time || '';
      draftWeek = cfg.work_weekdays.slice();
    }
    paintWeek();
    $('fHolidays').value = cfg.holidays.join('\n');
    $('fMakeup').value = cfg.makeup_workdays.join('\n');
    $('fItems').value = cfg.items.map(function (i) { return i.name + ',' + i.price; }).join('\n');
    $('advCount').textContent = cfg.items.length + ' 件';
    $('fDemo').checked = !!cfg.demo;
    draftTheme = cfg.theme;
    paintThemeSeg();
    $('fDemoTime').value = (cfg.demo && cfg.demo_offset) ? hhmmOf(minOfDate(nowAt())) : '';
    renderDemoChips();
    syncDemoUI(false);
    loadDeskOpts();          // 桌面版：刷新开机启动 / 检查更新的真实状态
    switchTab('work');       // 每次打开都从第一页开始，别停在上次那一页
    sheet.classList.add('open');
    fitPanelBody();          // 六页共用「工时」那一页的高度，切页不再跳
    syncLock();
    if (!firstRun) refreshUpdateRow();   // 每次打开设置都查一遍有没有新版本
    if (firstRun) setTimeout(function () { try { $('fSalary').focus(); } catch (e) {} }, 260);
  }

  function closeSheet() {
    if (firstRun) return;        // 首次设置不许跳过
    // 面板里试过的主题没保存，关掉就退回已保存的那个
    if (draftTheme !== cfg.theme) { draftTheme = cfg.theme; applyTheme(cfg.theme); }
    sheet.classList.remove('open');
    syncLock();
  }

  $('btnCfg').addEventListener('click', function () { if (!firstRun) openSheet(false); });

  // 顶栏一键切主题：浅 / 深之间来回切，直接落盘，不用进设置面板。
  // 当前是"跟随系统"时按此刻实际看到的明暗切到对面——点一次就一定有变化，
  // 否则在深色系统下点"深色→深色"会以为按钮坏了。切完就不再跟随系统。
  $('btnTheme').addEventListener('click', function () {
    if (firstRun) return;        // 首次设置没填完，别把空配置写进库
    var nowDark = document.documentElement.getAttribute('data-theme') === 'dark';
    var next = nowDark ? 'light' : 'dark';
    cfg.theme = next;
    draftTheme = next;           // 面板里的草稿也跟上，免得关闭时把主题退回去
    G.saveCfg(cfg);              // 本地缓存（首帧用），权威数据写 SQLite
    desk.send('save_cfg', cfg);
    applyTheme(next);
    paintThemeSeg();
  });
  $('mask').addEventListener('click', closeSheet);
  $('btnCancel').addEventListener('click', closeSheet);

  // 演示时间：勾上才展开；点快捷时段只填值，点保存才生效（跟其他项一致）
  $('fDemo').addEventListener('change', function () { syncDemoUI(true); });
  $('fCloseExit').addEventListener('change', paintCloseHint);   // 勾选时立刻预览提示语
  $('fDemoTime').addEventListener('input', paintChips);
  $('btnDemoClear').addEventListener('click', function () {
    $('fDemoTime').value = '';
    paintChips();
  });
  $('demoChips').addEventListener('click', function (e) {
    var b = e.target && e.target.closest ? e.target.closest('button') : null;
    if (!b) return;
    $('fDemoTime').value = b.getAttribute('data-t');
    paintChips();
  });

  // 主题：点了立刻预览，保存才落盘（跟面板里其他项的手感一致）
  $('fTheme').addEventListener('click', function (e) {
    var b = e.target && e.target.closest ? e.target.closest('button') : null;
    if (!b) return;
    var v = b.getAttribute('data-theme-opt');
    if (!v) return;
    draftTheme = (v === 'light' || v === 'dark') ? v : 'system';
    applyTheme(draftTheme);
    paintThemeSeg();
  });

  weekBtns.forEach(function (b) {
    b.addEventListener('click', function () {
      var n = parseInt(b.getAttribute('data-w'), 10);
      var i = draftWeek.indexOf(n);
      if (i >= 0) {
        if (draftWeek.length === 1) return;  // 至少留一天
        draftWeek.splice(i, 1);
      } else {
        draftWeek.push(n);
        draftWeek.sort(function (a, b2) { return a - b2; });
      }
      paintWeek();
    });
  });

  function toMin(hhmm) {
    var t = G.parseHHMM(hhmm);
    return t ? t.h * 60 + t.mi : null;
  }

  // 返回 true 表示校验通过
  function validate() {
    clearErrors();
    var ok = true;

    var raw = String($('fSalary').value || '').replace(/[,，\s]/g, '');
    var pay = parseFloat(raw);
    if (!raw || !isFinite(pay) || pay <= 0) {
      showErr('salaryErr', raw ? '月薪要是大于 0 的数字' : '先填月薪，不然算不出钱', $('fSalary'));
      ok = false;
    }

    var s = toMin($('fStart').value), e = toMin($('fEnd').value);
    if (s === null || e === null) {
      showErr('timeErr', '上班和下班时间都要填', !s ? $('fStart') : $('fEnd'));
      ok = false;
    } else if (e <= s) {
      showErr('timeErr', '下班时间要晚于上班时间', $('fEnd'));
      ok = false;
    } else if (e - s < 60) {
      showErr('timeErr', '这一天不到 1 小时，检查一下时间填反了没', $('fEnd'));
      ok = false;
    }

    var bs = $('fBreakS').value, be = $('fBreakE').value;
    if (!!bs !== !!be) {
      showErr('breakErr', '午休两个时间要么都填，要么都留空', bs ? $('fBreakE') : $('fBreakS'));
      ok = false;
    } else if (bs && be && toMin(be) !== null && toMin(bs) !== null && toMin(be) <= toMin(bs)) {
      showErr('breakErr', '午休结束要晚于开始', $('fBreakE'));
      ok = false;
    }

    /* 发薪日：两格都留空 = 不要发薪倒计时，合法；只填一格要提示补全。
       填了就得是 1-31 的整数，外加一个到账时间。 */
    var pdRaw = String($('fPayDay').value || '').trim();
    var ptRaw = String($('fPayTime').value || '').trim();
    if (!pdRaw && !ptRaw) {
      // 都留空：主界面不显示这一行，通过
    } else if (!pdRaw) {
      showErr('payErr', '每月几号发工资要填一下，或者两格都留空', $('fPayDay'));
      ok = false;
    } else if (!/^\d{1,2}$/.test(pdRaw) || !(parseInt(pdRaw, 10) >= 1 && parseInt(pdRaw, 10) <= 31)) {
      showErr('payErr', '发薪日要填 1 到 31 之间的整数', $('fPayDay'));
      ok = false;
    } else if (!ptRaw) {
      showErr('payErr', '发薪时间也要填（几点到账），或者两格都留空', $('fPayTime'));
      ok = false;
    }
    return ok;
  }

  $('btnSave').addEventListener('click', function () {
    if (!validate()) {
      var first = panel.querySelector('.err.on');
      if (first) {
        // 出错的项可能在别的标签页上，先跳过去再滚到它
        var pane = first.closest ? first.closest('.tab-pane') : null;
        var name = pane ? pane.getAttribute('data-pane') : '';
        if (name && name !== curTab) switchTab(name);
        first.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
      return;
    }
    var pay = parseFloat(String($('fSalary').value).replace(/[,，\s]/g, ''));
    cfg = G.normalize({
      monthly_salary: pay,
      work_start: $('fStart').value,
      work_end: $('fEnd').value,
      break_start: $('fBreakS').value,
      break_end: $('fBreakE').value,
      pay_day: String($('fPayDay').value || '').trim() ? parseInt(String($('fPayDay').value).trim(), 10) : 0,
      pay_time: String($('fPayDay').value || '').trim() ? $('fPayTime').value : '',
      work_weekdays: draftWeek,
      holidays: $('fHolidays').value,
      makeup_workdays: $('fMakeup').value,
      items: $('fItems').value,
      demo: $('fDemo').checked,
      demo_offset: ($('fDemo').checked && $('fDemoTime').value) ? offsetOfHHMM($('fDemoTime').value) : 0,
      theme: draftTheme,
      display: { hide_money: cfg.display.hide_money }
    });
    G.saveCfg(cfg);            // 本地缓存（首帧用），权威数据写 SQLite
    G.markReady();
    desk.send('save_cfg', cfg);
    applyTheme(cfg.theme);   // 已保存值可能和预览值相同，重放一次不会有副作用
    saveDeskOpts();          // 开机启动 / 检查更新交由桌面层落到系统里
    firstRun = false;
    panel.classList.remove('setup');
    document.body.classList.remove('firstrun');
    sheet.classList.remove('open');
    syncLock();
    start();
    refs.hideTxt.textContent = cfg.display.hide_money ? '显示金额' : '隐藏金额';
  });

  // 首次设置：在输入框里按回车直接保存，填完最后一项不用再去点按钮
  panel.addEventListener('keydown', function (e) {
    if (!firstRun || e.key !== 'Enter' || e.shiftKey) return;
    var t = e.target;
    if (!t || t.tagName !== 'INPUT') return;
    e.preventDefault();
    $('btnSave').click();
  });

  // 清空输入时的错误提示，别让红字一直挂着
  ['fSalary', 'fStart', 'fEnd', 'fBreakS', 'fBreakE', 'fPayDay', 'fPayTime'].forEach(function (id) {
    $(id).addEventListener('input', function () {
      this.style.borderColor = '';
      clearErrors();
    });
  });

  $('btnReset').addEventListener('click', function () {
    if (!confirm('清空现在填的薪资和时间，重新设置一遍？\n日历里写的备注也会一起清掉。')) return;
    G.resetSaved();
    desk.send('reset_store');      // SQLite 里的配置和备注一并清空
    notes = {}; notesKey = ''; calKey = '';
    cfg = G.normalize({});
    // 配置清空 = 主题也回到默认，别让界面停在用户刚选的浅/深色上
    draftTheme = cfg.theme;
    applyTheme(cfg.theme);
    refs.hideTxt.textContent = '隐藏金额';
    openSheet(true);          // 重设 = 再走一次首次引导
  });

  /* ---------- 桌面程序桥接 ----------
     直接在浏览器里打开这个 HTML 时没有 window.pywebview，下面整段静默跳过：
     界面照常用，只是没有开机启动、托盘和更新提示。 */
  var desk = (function () {
    function api() {
      var p = window.pywebview;
      return (p && p.api) ? p.api : null;
    }
    function call(name, arg) {
      var a = api();
      if (!a || typeof a[name] !== 'function') return null;
      try {
        // 不能无条件写 a[name](arg)：arg 为 undefined 时也会算一个实参，Python 侧就多收一个 None
        return (arg === undefined) ? a[name]() : a[name](arg);
      } catch (e) {
        return null;
      }
    }
    return {
      ready: function () { return !!api(); },
      call: call,
      // 只负责发出去，不等回执：桌面接口出问题也不该影响计时
      send: function (name, arg) {
        var r = call(name, arg);
        if (r && typeof r.then === 'function') r.then(null, function () {});
        return r;
      }
    };
  })();

  var deskOpts = null;

  function escHtml(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return c === '&' ? '&amp;' : c === '<' ? '&lt;' : c === '>' ? '&gt;' : '&quot;';
    });
  }

  // 托盘用的快照。Python 侧会按这份数据继续外推已赚和剩余时间，
  // 因为窗口藏起来以后系统会节流页面里的定时器。
  function statusPayload() {
    var snap = engine.snapshot(nowAt(), cfg.demo);
    return {
      status: snap.status,
      working: snap.status === '上班中',
      earned: snap.earned,
      rate: snap.speed,
      worked: snap.worked,
      remain: snap.remaining,
      masked: !!cfg.display.hide_money
    };
  }

  function pushStatus() {
    if (!running) return;
    desk.send('push_status', statusPayload());
  }

  /* ---------- 到点提醒 ----------
     界面负责判断"刚跨过哪个时点"，弹通知交给桌面层（Python 侧调系统托盘气泡）。
     在浏览器里直接打开时没有桥，这段就是空转。 */
  var NOTICE_KEY = 'guliqi.notices.v1';
  var noticeLog = loadNoticeLog();
  var lastPhase = '';

  function loadNoticeLog() {
    try {
      var raw = localStorage.getItem(NOTICE_KEY);
      var data = raw ? JSON.parse(raw) : null;
      return (data && typeof data === 'object') ? data : {};
    } catch (e) { return {}; }
  }

  function dayStamp(d) {
    return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
  }

  // 同一天里同一种提醒只弹一次；顺便把往天的记录扔掉，别越攒越多
  function claimNotice(kind, now) {
    var day = dayStamp(now);
    var key = day + '|' + kind;
    if (noticeLog[key]) return false;
    var fresh = {};
    fresh[key] = 1;
    for (var k in noticeLog) {
      if (k.indexOf(day + '|') === 0) fresh[k] = 1;
    }
    noticeLog = fresh;
    try { localStorage.setItem(NOTICE_KEY, JSON.stringify(noticeLog)); } catch (e) {}
    return true;
  }

  function phaseOf(snap) {
    if (!snap.isWorkday) return 'rest';
    if (snap.status === '未开工') return 'before';
    if (snap.status === '小憩') return 'lunch';
    if (snap.status === '已下班') return 'off';
    return 'work';
  }

  function trackPhase(snap) {
    var phase = phaseOf(snap);
    if (!lastPhase) {            // 刚启动时不做补发，只记住当前在哪一段
      lastPhase = phase;
      return;
    }
    if (phase === lastPhase) return;

    var from = lastPhase;
    lastPhase = phase;

    // 演示模式的"现在"是假的，不拿它打扰人
    if (cfg.demo) return;

    var kind = '';
    if (phase === 'lunch' && from === 'work') kind = 'lunch';
    else if (phase === 'work' && from === 'lunch') kind = 'lunch_end';
    else if (phase === 'off' && (from === 'work' || from === 'lunch')) kind = 'off';
    if (!kind) return;
    if (!claimNotice(kind, snap.now)) return;

    desk.send('notify_event', {
      kind: kind,
      earned: snap.earned,
      remain: snap.remaining,
      masked: !!cfg.display.hide_money
    });
  }

  /* ---------- 更新提示 ---------- */
  var updateUrl = '';
  var updateTag = '';
  var updateDismissed = '';
  var lastUpdateAt = 0;      // 上次拿到结果的时间戳，用来判断"这次查完了没"

  function showUpdate(info) {
    if (info && info.at) lastUpdateAt = info.at;
    if (!info || !info.newer || !info.tag) return;
    if (updateDismissed === info.tag) return;
    updateTag = info.tag;
    updateUrl = info.url || '';
    $('updateTxt').innerHTML = '发现新版本 <b>' + escHtml(info.tag) + '</b>'
      + '，当前 v' + escHtml(info.current);
    $('updateBar').classList.add('on');
  }

  $('btnUpdateGo').addEventListener('click', function () {
    if (updateUrl) desk.send('open_url', updateUrl);
  });

  $('btnUpdateClose').addEventListener('click', function () {
    updateDismissed = updateTag;
    $('updateBar').classList.remove('on');
  });

  function pollUpdate() {
    var p = desk.call('poll_update');
    if (!p || typeof p.then !== 'function') return;
    p.then(function (info) { if (info) showUpdate(info); }, function () {});
  }

  /* ---------- 全局 toast ----------
     一次性提示（查更新结果等）从底部浮出，2.8 秒后自己消失。
     替代原先贴在版本号旁边的 verMsg——那会跟底栏布局抢地方。 */
  var toastTimer = null;

  function toast(text) {
    var el = $('toast');
    el.textContent = text;
    el.classList.add('on');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('on'); }, 2800);
  }

  (function () {
    var btn = $('verNum');
    var baseVer = btn.textContent;

    btn.addEventListener('click', function () {
      if (btn.classList.contains('busy')) return;
      if (!desk.ready()) { toast('桌面版才能查更新'); return; }

      var base = lastUpdateAt;
      btn.classList.add('busy');
      btn.textContent = '检查中…';
      desk.send('check_update_now');

      var tries = 0;
      (function wait() {
        tries++;
        var p = desk.call('poll_update');
        if (!p || typeof p.then !== 'function') {
          btn.classList.remove('busy');
          btn.textContent = baseVer;
          return;
        }
        p.then(function (info) {
          if (info && info.at && info.at > base) {
            btn.classList.remove('busy');
            btn.textContent = 'v' + (info.current || baseVer.replace(/^v/, ''));
            lastUpdateAt = info.at;
            if (info.newer) { showUpdate(info); toast('发现新版本 ' + info.tag); }
            else toast('已是最新版本 v' + (info.current || ''));
          } else if (tries < 16) {
            setTimeout(wait, 700);
          } else {
            btn.classList.remove('busy');
            btn.textContent = baseVer;
            toast('网络不通，待会儿再试');
          }
        }, function () {
          btn.classList.remove('busy');
          btn.textContent = baseVer;
        });
      })();
    });
  })();

  /* ---------- 关于 ---------- */
  function paintAbout(opts) {
    var v = (opts && opts.version) || '';
    if (v) {
      $('verNum').textContent = 'v' + v;
      $('aboutVer').textContent = 'v' + v;
      $('aboutCur').textContent = 'v' + v;
    }
    if (opts && opts.data_dir) $('aboutDir').textContent = opts.data_dir;
  }

  /* 「更新」那一行：每次打开设置都静默查一遍（不进托盘通知）。
     有新版本 → 按钮变「点击下载新版」，点了开 Release；
     已是最新 → 变成不可点的「已经是最新版本」。 */
  var aboutUpdateUrl = '';

  function paintUpdateRow(info) {
    var btn = $('aboutUpdate');
    if (!btn) return;
    if (info && info.at) lastUpdateAt = info.at;
    if (info && info.current) {
      $('aboutCur').textContent = 'v' + info.current;
      $('aboutVer').textContent = 'v' + info.current;
    }
    aboutUpdateUrl = '';
    if (info && info.newer && info.tag) {
      aboutUpdateUrl = info.url || '';
      btn.textContent = '点击下载新版';
      btn.disabled = false;
      btn.title = '下载 ' + info.tag;
    } else {
      btn.textContent = '已经是最新版本';
      btn.disabled = true;
      btn.title = '';
    }
  }

  function refreshUpdateRow() {
    var btn = $('aboutUpdate');
    if (!btn) return;
    if (!desk.ready()) { btn.textContent = '桌面版才能检查更新'; btn.disabled = true; return; }
    btn.textContent = '检查中…';
    btn.disabled = true;
    btn.title = '';
    var base = lastUpdateAt;
    desk.send('check_update_quiet');
    var tries = 0;
    (function wait() {
      tries++;
      var p = desk.call('poll_update');
      if (!p || typeof p.then !== 'function') {
        btn.textContent = '检查更新失败';
        btn.disabled = false;
        return;
      }
      p.then(function (info) {
        if (info && info.at && info.at > base) paintUpdateRow(info);
        else if (tries < 12) setTimeout(wait, 600);
        else { btn.textContent = '检查超时，点此重试'; btn.disabled = false; }
      }, function () {
        btn.textContent = '检查更新失败';
        btn.disabled = false;
      });
    })();
  }

  $('aboutUpdate').addEventListener('click', function () {
    if (aboutUpdateUrl) { desk.send('open_url', aboutUpdateUrl); return; }
    refreshUpdateRow();
  });

  $('aboutDir').addEventListener('click', function () {
    if (!desk.ready()) { toast('桌面版才能打开目录'); return; }
    desk.send('open_data_dir');
  });

  // 「关于」里的链接按钮：统一交给桌面层用系统浏览器打开（只放行 github.com）
  panel.addEventListener('click', function (e) {
    var b = e.target && e.target.closest ? e.target.closest('.about-link') : null;
    if (!b) return;
    var url = b.getAttribute('data-url');
    if (!url) return;
    if (!desk.ready()) { toast('用桌面版才能打开链接'); return; }
    desk.send('open_url', url);
  });

  /* ---------- 桌面选项 ---------- */
  function paintCloseHint() {
    var el = $('deskHint');
    if (!el) return;
    el.textContent = $('fCloseExit').checked
      ? '点叉号会直接退出程序，计时随之结束。'
      : '点叉号不会退出，程序缩到右下角托盘继续计时；点托盘图标回到界面。';
  }

  function applyDeskOpts(opts) {
    if (!opts) return;
    deskOpts = opts;
    $('deskBox').style.display = '';
    $('fAutostart').checked = !!opts.autostart;
    $('fCheckUpdate').checked = !!opts.check_update;
    $('fNotify').checked = opts.notify_schedule !== false;
    $('fCloseExit').checked = !!opts.close_exit;
    paintCloseHint();
    paintAbout(opts);
    if (opts.update) showUpdate(opts.update);
  }

  function loadDeskOpts() {
    var p = desk.call('get_settings');
    if (!p || typeof p.then !== 'function') return;
    p.then(applyDeskOpts, function () {});
  }

  function saveDeskOpts() {
    if (!desk.ready()) return;
    desk.send('set_autostart', !!$('fAutostart').checked);
    desk.send('set_check_update', !!$('fCheckUpdate').checked);
    desk.send('set_notify_schedule', !!$('fNotify').checked);
    desk.send('set_close_exit', !!$('fCloseExit').checked);
  }

  /* ---------- 背景粒子 ----------
     46 个微光点缓慢上浮 + 轻微闪烁，透明度压得很低，
     只求「有东西在动」，不抢数字的戏。
     GPU 加速：画布本身是独立合成层（见 #bgFx 的 translateZ(0)），
     每帧只做 canvas 2D 绘制，浏览器把结果直接交给显卡合成；
     页面隐藏时暂停，系统开了「减少动态效果」时完全不跑。 */
  (function () {
    var cv = $('bgFx');
    if (!cv || !cv.getContext) return;
    var reduceMotion = false;
    try { reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}
    if (reduceMotion) return;

    var ctx = cv.getContext('2d');
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W = 0, H = 0;
    var N = 46, ps = [];

    // 两套配色各取一半：深色主题是金/青微光，浅色主题压深成淡金/淡蓝灰
    var COLORS_DARK = ['255,200,87', '78,205,196', '255,236,170'];
    var COLORS_LIGHT = ['176,132,32', '70,150,146', '120,130,160'];

    function palette() {
      return document.documentElement.getAttribute('data-theme') === 'light' ? COLORS_LIGHT : COLORS_DARK;
    }
    function baseAlpha() {
      return document.documentElement.getAttribute('data-theme') === 'light' ? 0.10 : 0.16;
    }
    function spawn(w, h) {
      return {
        x: Math.random() * w, y: Math.random() * h,
        r: 0.7 + Math.random() * 1.9,                                  // 半径（CSS px）
        vx: (Math.random() - 0.5) * 0.10,                              // 水平漂移
        vy: -(0.04 + Math.random() * 0.14),                            // 缓慢上浮
        tw: 0.4 + Math.random() * 0.9,                                 // 闪烁速度
        ph: Math.random() * Math.PI * 2,                               // 闪烁相位
        c: Math.floor(Math.random() * 3)
      };
    }
    function resize() {
      /* clientWidth/Height 才是"看得见的那块"，innerWidth 含滚动条宽度：
         用 innerWidth 铺画布会宽出十几像素，恰好逼出一条横向滚动条。 */
      W = document.documentElement.clientWidth || window.innerWidth;
      H = document.documentElement.clientHeight || window.innerHeight;
      // 拖到另一块屏幕上 DPR 会变，顺手跟上，别让粒子糊掉
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      cv.style.width = W + 'px'; cv.style.height = H + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    resize();
    for (var i = 0; i < N; i++) ps.push(spawn(W, H));

    var running = false, rafId = 0;
    function frame(t) {
      rafId = 0;
      var pal = palette(), A = baseAlpha();
      ctx.clearRect(0, 0, W, H);
      for (var i = 0; i < N; i++) {
        var p = ps[i];
        p.x += p.vx; p.y += p.vy;
        if (p.y < -6) { p.y = H + 6; p.x = Math.random() * W; }
        if (p.x < -6) p.x = W + 6; else if (p.x > W + 6) p.x = -6;
        var a = A * (0.55 + 0.45 * Math.sin(p.ph + t * 0.001 * p.tw));
        if (a <= 0.01) continue;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, 6.2832);
        ctx.fillStyle = 'rgba(' + pal[p.c] + ',' + a.toFixed(3) + ')';
        ctx.fill();
      }
      if (running && !document.hidden) rafId = requestAnimationFrame(frame);
    }
    function start() {
      if (running || document.hidden) return;
      running = true;
      if (!rafId) rafId = requestAnimationFrame(frame);
    }
    function stop() {
      running = false;
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      ctx.clearRect(0, 0, W, H);
    }

    /* 拖边框改尺寸时 resize 事件一帧能来好几次，而写 canvas.width 等于
       重新分配整块位图并清空画面 —— 一次拖拽里这么干十几遍，看起来就是闪。
       合并到下一次 rAF 里做，一个渲染帧最多重排一次；尺寸没真变就什么都不做。 */
    var rszId = 0;
    function onResize() {
      if (rszId) return;
      rszId = requestAnimationFrame(function () {
        rszId = 0;
        var w = document.documentElement.clientWidth || window.innerWidth;
        var h = document.documentElement.clientHeight || window.innerHeight;
        if (w === W && h === H && dpr === Math.min(window.devicePixelRatio || 1, 2)) return;
        resize();
        // 尺寸变了重撒粒子，避免全挤在旧区域
        for (var k = 0; k < N; k++) ps[k] = spawn(W, H);
      });
    }
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) stop(); else start();
    });
    start();
  })();

  /* ---------- 快捷键 ----------
     只保留 Esc 关面板。C/H 之类的单键快捷键已移除：
     选中文字想 Ctrl+C 时会误触发，得不偿失。 */
  document.addEventListener('keydown', function (e) {
    var t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) {
      if (e.key === 'Escape') closeSheet();
      return;
    }
    if (e.key === 'Escape') closeSheet();
  });

  /* ---------- 启动 ----------
     数据以 SQLite 为准：先问桌面层要一份，拿到就按它跑；
     v1.3.x 的老用户（只有 localStorage、库里还没有）自动迁一次；都没有才进首次引导。 */
  refs.hideTxt.textContent = cfg.display.hide_money ? '显示金额' : '隐藏金额';

  function firstRunUI() {
    // 首次进入：不启动计时、不显示任何金额，先把人拦在设置面板里
    document.body.classList.add('firstrun');
    openSheet(true);
  }

  function adopt(raw) {
    if (raw && typeof raw === 'object' && raw.monthly_salary !== undefined) {
      cfg = G.normalize(raw);
    }
    applyTheme(cfg.theme);
    refs.hideTxt.textContent = cfg.display.hide_money ? '显示金额' : '隐藏金额';
    start();
  }

  function bootLocal() {
    // 浏览器里直接打开（或桌面桥没起来）：退回 localStorage，功能照用，只是不落库
    paintDeskTab();              // 没有桥，「桌面」标签藏掉
    if (G.hasSaved()) start();
    else firstRunUI();
  }

  function boot() {
    if (!desk.ready()) { bootLocal(); return; }
    paintDeskTab();              // 桥就绪，「桌面」标签亮出来
    var p = desk.call('get_state');
    if (!p || typeof p.then !== 'function') { bootLocal(); return; }
    p.then(function (res) {
      if (!res) { bootLocal(); return; }
      // 桌面层记着上次窗口尺寸的话，这次就不自动收窗口了
      if (res.win_saved) winSaved = true;
      if (res.ready) {
        adopt(res.cfg);
      } else if (G.hasSaved()) {
        adopt(null);                 // 沿用 localStorage 里那份
        desk.send('save_cfg', cfg);  // 搬进 SQLite，之后就以库为准
      } else {
        firstRunUI();
      }
      if (res.opts) applyDeskOpts(res.opts);
    }, bootLocal);
  }

  // 桥可能比脚本晚就绪：先等 pywebviewready；纯浏览器直开时用超时兜底，别一直白屏等桥
  (function () {
    var booted = false;
    function go() {
      booted = true;
      boot();
    }
    if (desk.ready()) { go(); return; }
    window.addEventListener('pywebviewready', function () {
      if (booted && !desk.ready()) return;
      go();              // 桥晚到：再走一遍 boot，adopt 会按库里的数据重启引擎
    });
    setTimeout(function () { if (!booted) go(); }, 1200);
  })();

  /* ---------- 桌面集成：托盘数据 + 更新提示 ----------
     两个定时器在浏览器里也会跑，但 desk 为空时是空转，几乎零成本。 */
  window.addEventListener('pywebviewready', function () {
    loadDeskOpts();
    pushStatus();
    pollUpdate();
  });
  setInterval(pushStatus, 5000);
  setInterval(pollUpdate, 8000);
  // 兜底：pywebviewready 可能在本脚本执行前就发过了
  setTimeout(function () {
    loadDeskOpts();
    pollUpdate();
    pushStatus();
  }, 2500);
})();
