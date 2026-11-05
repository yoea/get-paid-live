/* 公历 -> 农历 + 节日，给日历格子的小字用。
   数据表是公开的 1900-2100 农历压缩表（每年一个 hex：高 12 位是 12 个月的大小月，
   第 16 位是闰月大小，低 4 位是闰月月份；基准 1900-01-31 = 农历正月初一）。
   只做「显示农历日期和传统节日」这一件事，不含节气、吉凶之类。 */
var Lunar = (function () {
  'use strict';

  var LUNAR_INFO = [
  0x04bd8,0x04ae0,0x0a570,0x054d5,0x0d260,0x0d950,0x16554,0x056a0,0x09ad0,0x055d2,    // 1900-1909
  0x04ae0,0x0a5b6,0x0a4d0,0x0d250,0x1d255,0x0b540,0x0d6a0,0x0ada2,0x095b0,0x14977,    // 1910-1919
  0x04970,0x0a4b0,0x0b4b5,0x06a50,0x06d40,0x1ab54,0x02b60,0x09570,0x052f2,0x04970,    // 1920-1929
  0x06566,0x0d4a0,0x0ea50,0x06e95,0x05ad0,0x02b60,0x186e3,0x092e0,0x1c8d7,0x0c950,    // 1930-1939
  0x0d4a0,0x1d8a6,0x0b550,0x056a0,0x1a5b4,0x025d0,0x092d0,0x0d2b2,0x0a950,0x0b557,    // 1940-1949
  0x06ca0,0x0b550,0x15355,0x04da0,0x0a5b0,0x14573,0x052b0,0x0a9a8,0x0e950,0x06aa0,    // 1950-1959
  0x0aea6,0x0ab50,0x04b60,0x0aae4,0x0a570,0x05260,0x0f263,0x0d950,0x05b57,0x056a0,    // 1960-1969
  0x096d0,0x04dd5,0x04ad0,0x0a4d0,0x0d4d4,0x0d250,0x0d558,0x0b540,0x0b6a0,0x195a6,    // 1970-1979
  0x095b0,0x049b0,0x0a974,0x0a4b0,0x0b27a,0x06a50,0x06d40,0x0af46,0x0ab60,0x09570,    // 1980-1989
  0x04af5,0x04970,0x064b0,0x074a3,0x0ea50,0x06b58,0x05ac0,0x0ab60,0x096d5,0x092e0,    // 1990-1999
  0x0c960,0x0d954,0x0d4a0,0x0da50,0x07552,0x056a0,0x0abb7,0x025d0,0x092d0,0x0cab5,    // 2000-2009
  0x0a950,0x0b4a0,0x0baa4,0x0ad50,0x055d9,0x04ba0,0x0a5b0,0x15176,0x052b0,0x0a930,    // 2010-2019
  0x07954,0x06aa0,0x0ad50,0x05b52,0x04b60,0x0a6e6,0x0a4e0,0x0d260,0x0ea65,0x0d530,    // 2020-2029
  0x05aa0,0x076a3,0x096d0,0x04afb,0x04ad0,0x0a4d0,0x1d0b6,0x0d250,0x0d520,0x0dd45,    // 2030-2039
  0x0b5a0,0x056d0,0x055b2,0x049b0,0x0a577,0x0a4b0,0x0aa50,0x1b255,0x06d20,0x0ada0,    // 2040-2049
  /**Add By JJonline@JJonline.Cn**/
  0x14b63,0x09370,0x049f8,0x04970,0x064b0,0x168a6,0x0ea50,0x06b20,0x1a6c4,0x0aae0,    // 2050-2059
  0x092e0,0x0d2e3,0x0c960,0x0d557,0x0d4a0,0x0da50,0x05d55,0x056a0,0x0a6d0,0x055d4,    // 2060-2069
  0x052d0,0x0a9b8,0x0a950,0x0b4a0,0x0b6a6,0x0ad50,0x055a0,0x0aba4,0x0a5b0,0x052b0,    // 2070-2079
  0x0b273,0x06930,0x07337,0x06aa0,0x0ad50,0x14b55,0x04b60,0x0a570,0x054e4,0x0d160,    // 2080-2089
  0x0e968,0x0d520,0x0daa0,0x16aa6,0x056d0,0x04ae0,0x0a9d4,0x0a4d0,0x0d150,0x0f252,    // 2090-2099
  0x0d520  // 2100
  ];

  var MONTH_CN = ['正','二','三','四','五','六','七','八','九','十','冬','腊'];
  var DAY_CN = ['初一','初二','初三','初四','初五','初六','初七','初八','初九','初十',
                '十一','十二','十三','十四','十五','十六','十七','十八','十九','二十',
                '廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十'];
  var MONTH_FULL = ['正月','二月','三月','四月','五月','六月','七月','八月','九月','十月','冬月','腊月'];

  /* 公历节日：月-日 -> 名 */
  var SOLAR_FEST = {
    '1-1': '元旦', '2-14': '情人节', '3-8': '妇女节', '3-12': '植树节',
    '5-1': '劳动节', '5-4': '青年节', '6-1': '儿童节', '7-1': '建党节',
    '8-1': '建军节', '9-10': '教师节', '10-1': '国庆节', '12-24': '平安夜',
    '12-25': '圣诞节'
  };
  /* 农历节日：月-日 -> 名（除夕特殊，见 festivalOf） */
  var LUNAR_FEST = {
    '1-1': '春节', '1-15': '元宵', '2-2': '龙抬头', '5-5': '端午',
    '7-7': '七夕', '7-15': '中元', '8-15': '中秋', '9-9': '重阳',
    '12-8': '腊八'
  };

  function yearDays(y) {
    var sum = 348;
    for (var i = 0x8000; i > 0x8; i >>= 1) sum += (LUNAR_INFO[y - 1900] & i) ? 1 : 0;
    // 第 16 位是"闰月的大小"：没有闰月的年份不能加这 29/30 天
    return sum + (leapMonth(y) ? ((LUNAR_INFO[y - 1900] & 0x10000) ? 30 : 29) : 0);
  }
  function leapMonth(y) { return LUNAR_INFO[y - 1900] & 0xf; }
  function leapDays(y) { return leapMonth(y) ? ((LUNAR_INFO[y - 1900] & 0x10000) ? 30 : 29) : 0; }
  function monthDays(y, m) { return (LUNAR_INFO[y - 1900] & (0x10000 >> m)) ? 30 : 29; }

  /* 返回 {y,m,d,leap}，农历月、日都从 1 计；超出 1901-2099 返回 null（表边界外不可靠） */
  function solarToLunar(date) {
    var y = date.getFullYear(), mo = date.getMonth() + 1, d = date.getDate();
    if (y < 1901 || y > 2099) return null;
    var offset = Math.floor((Date.UTC(y, mo - 1, d) - Date.UTC(1900, 0, 31)) / 86400000);
    var i, temp = 0, year = 1900;
    for (i = 1900; i < 2101 && offset > 0; i++) { temp = yearDays(i); offset -= temp; }
    if (offset < 0) { offset += temp; i--; }
    year = i;
    var leap = leapMonth(year), isLeap = false, month = 1;
    for (month = 1; month < 13 && offset > 0; month++) {
      if (leap > 0 && month === leap + 1 && !isLeap) {
        --month; isLeap = true; temp = leapDays(year);
      } else {
        temp = monthDays(year, month);
      }
      if (isLeap && month === leap + 1) isLeap = false;
      offset -= temp;
    }
    if (offset === 0 && leap > 0 && month === leap + 1) {
      if (isLeap) { isLeap = false; } else { isLeap = true; --month; }
    }
    if (offset < 0) { offset += temp; --month; }
    return { y: year, m: month, d: offset + 1, leap: isLeap };
  }

  /* 日历小字：节日名优先，其次是农历日（初一显示月名，如「九月」） */
  function dayLabel(date) {
    var l = solarToLunar(date);
    if (!l) return null;
    var fest = LUNAR_FEST[l.m + '-' + l.d];
    if (!fest && l.m === 12) {
      // 除夕 = 腊月的最后一天（明天是正月初一）
      var next = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1);
      var nl = solarToLunar(next);
      if (nl && nl.m === 1 && nl.d === 1 && !nl.leap) fest = '除夕';
    }
    if (!fest) fest = SOLAR_FEST[date.getMonth() + 1 + '-' + date.getDate()];
    var day = l.d === 1 ? MONTH_FULL[l.m - 1] : DAY_CN[l.d - 1];
    return {
      text: fest || day,
      festival: !!fest,
      monthCn: (l.leap ? '闰' : '') + MONTH_CN[l.m - 1] + '月',
      dayCn: DAY_CN[l.d - 1]
    };
  }

  return { solarToLunar: solarToLunar, dayLabel: dayLabel };
})();
