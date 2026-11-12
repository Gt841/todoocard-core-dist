/* todoocard-core-dist 2.0.5 —— 原生控制台多设备增强（内联注入 web/card.html）。
 *
 * 目标：
 *   1) 「设备与配对」页扫描/绑定 UUID 时可以直接登记别名 + 蓝牙 MAC；
 *   2) 登记了多台卡时，点「发送这个模板」先让用户手动选发到哪台；
 *      只有一台（或没登记）时不弹选择，直接发送。
 *
 * 依赖：上游 card.html 的全局 toast / load / send / useDevice / scanDevices，
 * 以及扩展 2.0.4 提供的 /api/card/devices* 接口。后端没有 2.0.4 时全部降级：
 * 不弹选择、登记区显示「未启用」，原有单卡流程不受影响。
 * 复用 2.0.3 的精确绑定：按别名切换会把该别名登记过的 UUID 全部写回 device_id。
 */
(function () {
  'use strict';

  const G = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
  const say = m => { try { toast(m); } catch (e) { /* 上游未定义 toast 时忽略 */ } };

  let reg = {
    devices: [], device_alias: '', device_id: '', device_name: '',
    sync_file: '', sync_exists: false, available: false
  };

  async function api(url, body) {
    try {
      const r = await fetch(url, {
        method: body ? 'POST' : 'GET',
        headers: body ? { 'Content-Type': 'application/json' } : {},
        body: body ? JSON.stringify(body) : undefined,
        cache: 'no-store'
      });
      const d = await r.json();
      return d || {};
    } catch (e) {
      return { ok: false, error: '接口不可用（需要扩展 2.0.4 以上）' };
    }
  }

  async function refresh() {
    const d = await api('/api/card/devices');
    if (d && d.ok) {
      reg = {
        devices: d.devices || [], device_alias: d.device_alias || '',
        device_id: d.device_id || '', device_name: d.device_name || '',
        sync_file: d.sync_file || '', sync_exists: !!d.sync_exists, available: true
      };
    } else {
      reg.available = false;
    }
    render();
    return reg;
  }

  function msg(text, bad) {
    const el = G('tdMsg');
    if (!el) return;
    el.textContent = text || '';
    el.style.color = bad ? 'var(--danger)' : 'var(--sub)';
  }

  function render() {
    const target = G('tdTarget');
    const list = G('tdList');
    if (!target || !list) return;

    if (!reg.available) {
      target.innerHTML = '<span style="color:var(--danger)">多设备接口未启用：请在插件控制台点「强制重装」升级核心扩展。</span>';
      list.innerHTML = '';
      return;
    }

    const n = reg.devices.length;
    const cur = reg.devices.filter(d => d.alias === reg.device_alias)[0];
    const sync = reg.sync_exists
      ? '注册表已写入思源工作区（随思源备份同步）'
      : '尚未写入思源备份同步文件（登记后自动生成）';
    target.innerHTML =
      '<div><b>当前目标：</b>' + (cur ? esc(cur.alias) + (cur.mac ? '（' + esc(cur.mac) + '）' : '')
        : (reg.device_id ? '未登记别名 · 直接按 UUID 绑定' : '未绑定')) +
      ' · 已登记 <b>' + n + '</b> 台</div>' +
      '<div class="hint">发送时' + (n >= 2 ? '会先让你选择发到哪张卡' : '只有一张卡，不再询问，直接发送') +
      '；' + esc(sync) + '</div>';

    if (!n) {
      list.innerHTML = '<div class="hint" style="margin-top:8px">还没有登记卡片。扫描后点「填入登记」，或直接给当前已绑定的 UUID 起个名字。</div>';
      return;
    }
    list.innerHTML = reg.devices.map((d, i) =>
      '<div class="dev" style="margin-top:8px">' +
        '<div><b>' + esc(d.alias) + '</b> · ' + esc(d.mac || '未填 MAC') +
        ' · ' + d.uuids.length + ' 个 UUID' +
        (d.alias === reg.device_alias ? ' <span class="pill on">当前</span>' : '') + '</div>' +
        '<div class="hint">' + (d.uuids.length ? d.uuids.map(esc).join('<br>') : '（还没登记 UUID，不能设为当前）') + '</div>' +
        '<div style="margin-top:6px;display:flex;gap:8px;flex-wrap:wrap">' +
          '<button data-td="select" data-i="' + i + '">设为当前</button>' +
          '<button data-td="del" data-i="' + i + '">删除</button>' +
        '</div>' +
      '</div>'
    ).join('');
  }

  const BOX_HTML =
    '<div id="tdBox" style="margin:14px 0;padding:14px;border:1px dashed var(--line);border-radius:12px;background:var(--panel2)">' +
      '<div style="font-size:13.5px;font-weight:650;margin-bottom:8px">登记别名（绑定 UUID ↔ 蓝牙 MAC）</div>' +
      '<div id="tdTarget" class="hint">读取中…</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">' +
        '<input id="tdAlias" placeholder="别名，如 客厅卡" style="flex:1;min-width:130px">' +
        '<input id="tdMac" placeholder="蓝牙 MAC，如 FFFF99803616（可选）" style="flex:1.4;min-width:180px">' +
      '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">' +
        '<input id="tdUuid" placeholder="macOS UUID（点扫描结果「填入登记」；留空则用当前已绑定的）" style="flex:3;min-width:240px">' +
      '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px">' +
        '<button class="primary" id="tdRegister">登记并设为当前</button>' +
        '<button id="tdOnly">只登记</button>' +
        '<button id="tdReload">从思源备份重新载入</button>' +
        '<a href="/devices" target="_blank" style="color:var(--accent);font-size:12.5px">打开完整管理页</a>' +
      '</div>' +
      '<div id="tdMsg" class="hint" style="margin-top:8px"></div>' +
      '<div class="hint" style="margin-top:4px">MAC 在手机小程序里看（FFFF99803616 = FF:FF:99:80:36:16），或本机执行 system_profiler SPBluetoothDataType。macOS 的 UUID 会轮换，出现新 UUID 时用「填入登记」再登记一次即可自动合并到同一别名。</div>' +
      '<div id="tdList"></div>' +
    '</div>';

  // ── 登记 / 切换 / 删除 ────────────────────────────────────────────────
  async function register(select) {
    const alias = (G('tdAlias').value || '').trim();
    const mac = (G('tdMac').value || '').trim();
    const uuid = (G('tdUuid').value || '').trim() || (reg.device_id || '').split(',')[0].trim();
    if (!alias) { msg('请先填一个别名，例如「客厅卡」', true); return; }
    const d = await api('/api/card/devices/register', { alias, mac, uuid, name: '', select: !!select });
    if (!d.ok) { msg(d.error || '登记失败', true); return; }
    say(select ? '已登记「' + alias + '」并设为当前' : '已登记「' + alias + '」');
    msg(select ? '已设为当前发送目标。' : '登记完成，发送前可在列表里「设为当前」。');
    G('tdAlias').value = ''; G('tdMac').value = ''; G('tdUuid').value = '';
    await refresh();
    if (window.load) window.load();
  }

  async function selectAlias(alias) {
    const d = await api('/api/card/devices/select', { alias });
    if (!d.ok) { say(d.error || '切换失败'); return false; }
    await refresh();
    if (window.load) window.load();
    return true;
  }

  function bindBox() {
    const box = G('tdBox');
    if (!box) return;
    G('tdRegister').onclick = () => register(true);
    G('tdOnly').onclick = () => register(false);
    G('tdReload').onclick = async () => {
      const d = await api('/api/card/devices/reload', {});
      if (!d.ok) { msg(d.error || '重新载入失败', true); return; }
      say('已从思源备份恢复注册表');
      msg('已从 ' + (d.sync_file || '思源备份同步文件') + ' 恢复。换机后 UUID 可能不同，扫描到新 UUID 请再登记一次。');
      await refresh();
      if (window.load) window.load();
    };
    G('tdList').addEventListener('click', async ev => {
      const btn = ev.target.closest('[data-td]');
      if (!btn) return;
      const d = reg.devices[Number(btn.getAttribute('data-i'))];
      if (!d) return;
      if (btn.getAttribute('data-td') === 'select') {
        const ok = await selectAlias(d.alias);
        msg(ok ? '当前目标：' + d.alias : '切换失败', !ok);
      } else if (btn.getAttribute('data-td') === 'del') {
        if (!window.confirm('删除别名「' + d.alias + '」的登记？（不会删除卡片本身）')) return;
        const r = await api('/api/card/devices/remove', { alias: d.alias });
        if (!r.ok) { msg(r.error || '删除失败', true); return; }
        say('已删除「' + d.alias + '」');
        await refresh();
        if (window.load) window.load();
      }
    });
  }

  // ── 扫描结果：结构化 + 每台都能「填入登记」 ────────────────────────────
  const origScan = window.scanDevices;
  window.scanDevices = async function () {
    const out = G('scanResult');
    if (!out) return origScan ? origScan() : undefined;
    out.innerHTML = '<div class="hint">扫描中，约 8 秒…长按卡片背面按钮 5 秒唤醒要绑定的那台</div>';
    const d = await api('/api/card/devices/scan', {});
    if (!d.ok) {
      if (origScan) return origScan();   // 后端没装 2.0.4 → 退回上游原生扫描
      out.innerHTML = '<div class="hint" style="color:var(--danger)">' + esc(d.error || '扫描失败') + '</div>';
      return;
    }
    await refresh();
    const found = d.found || [];
    if (!found.length) {
      out.innerHTML = '<div class="hint">没扫到兼容设备。长按卡片背面按钮 5 秒再扫一次（两台卡不要同时唤醒）。</div>';
      return;
    }
    out.innerHTML = found.map(f =>
      '<div class="dev" style="margin-top:8px">' +
        '<div>' + esc(f.name || 'TodooCard') + ' · rssi ' + esc(f.rssi) + '</div>' +
        '<div class="hint">' + esc(f.addr) + ' · ' +
          (f.owner ? '已登记为「' + esc(f.owner) + '」' : '<b style="color:var(--warm)">未登记</b>') +
        '</div>' +
        '<div style="margin-top:6px;display:flex;gap:8px;flex-wrap:wrap">' +
          '<button data-scan="use" data-u="' + esc(f.addr) + '">用这台</button>' +
          '<button data-scan="fill" data-u="' + esc(f.addr) + '">填入登记</button>' +
        '</div>' +
      '</div>'
    ).join('');
    out.onclick = ev => {
      const btn = ev.target.closest('[data-scan]');
      if (!btn) return;
      const u = btn.getAttribute('data-u');
      if (btn.getAttribute('data-scan') === 'fill') {
        G('tdUuid').value = u;
        G('tdAlias').focus();
        msg('已填入 ' + u + '，再填别名（可选填 MAC）后点「登记并设为当前」。');
      } else {
        window.useDevice(u);
      }
    };
  };

  // 「用这台」：填了别名就一步完成「绑定 UUID + 登记别名」，否则保留原行为并引导登记
  const origUse = window.useDevice;
  window.useDevice = async function (id) {
    const uuid = String(id || '').trim().toUpperCase();
    const alias = (G('tdAlias') && G('tdAlias').value.trim()) || '';
    if (alias) {
      const mac = (G('tdMac') && G('tdMac').value.trim()) || '';
      const d = await api('/api/card/devices/register',
        { alias, mac, uuid, name: '', select: true });
      if (!d.ok) { say(d.error || '登记失败'); msg(d.error || '登记失败', true); return; }
      say('已绑定并登记「' + alias + '」');
      msg('已设为当前发送目标。');
      G('tdAlias').value = ''; G('tdMac').value = ''; G('tdUuid').value = '';
      await refresh();
      if (window.load) window.load();
      return;
    }
    if (origUse) await origUse(uuid);
    if (G('tdUuid')) G('tdUuid').value = uuid;
    await refresh();
    msg('已绑定 UUID ' + uuid + '。填个别名再点「登记并设为当前」，以后就能按名字选卡。');
  };

  // ── 发送前选择目标：只有登记了 ≥2 台才弹 ───────────────────────────────
  function pickDevice(devices) {
    return new Promise(resolve => {
      const wrap = document.createElement('div');
      wrap.id = 'tdPicker';
      wrap.style.cssText = 'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;' +
        'justify-content:center;background:rgba(0,0,0,.6);padding:20px';
      wrap.innerHTML =
        '<div style="background:var(--panel);border:1px solid var(--line);border-radius:16px;' +
          'padding:18px;width:min(480px,100%);max-height:80vh;overflow:auto">' +
          '<div style="font-size:15px;font-weight:650;margin-bottom:6px">发到哪张卡？</div>' +
          '<div class="hint">登记了 ' + devices.length + ' 台设备，请选本次发送的目标；选择后会只连这张卡，绝不 fallback 到另一台。</div>' +
          '<div style="margin-top:12px">' + devices.map(d =>
            '<button data-pick="' + esc(d.alias) + '" style="display:block;width:100%;text-align:left;margin-bottom:8px">' +
              '<b>' + esc(d.alias) + '</b> · ' + esc(d.mac || '未填 MAC') +
              ' · ' + d.uuids.length + ' 个 UUID' +
              (d.alias === reg.device_alias ? ' <span class="pill on">当前</span>' : '') +
            '</button>').join('') + '</div>' +
          '<button data-cancel style="margin-top:6px">取消发送</button>' +
        '</div>';
      document.body.appendChild(wrap);
      const done = v => { wrap.remove(); resolve(v); };
      wrap.addEventListener('click', async ev => {
        const hit = ev.target.closest('[data-pick]');
        if (hit) {
          const ok = await selectAlias(hit.getAttribute('data-pick'));
          if (ok) done(true);
          return;
        }
        if (ev.target.closest('[data-cancel]') || ev.target === wrap) done(false);
      });
    });
  }

  async function ensureTarget() {
    await refresh();
    if (!reg.available || reg.devices.length < 2) return true;  // 0/1 台：不打扰，直接发
    return pickDevice(reg.devices);
  }

  const origSend = window.send;
  window.send = async function (kind) {
    if (!(await ensureTarget())) return;
    return origSend ? origSend(kind) : undefined;
  };
  if (typeof window.runNow === 'function') {
    const origRunNow = window.runNow;
    window.runNow = async function (kind) {
      if (!(await ensureTarget())) return;
      return origRunNow(kind);
    };
  }

  // ── 挂载 ──────────────────────────────────────────────────────────────
  function init() {
    const anchor = G('scanResult');
    if (!anchor || G('tdBox')) return;
    anchor.insertAdjacentHTML('beforebegin', BOX_HTML);
    bindBox();
    refresh();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
