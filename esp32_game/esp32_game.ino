// =====================================================================================
//  ESP32 all-in-one: Wi-Fi signal page + Wi-Fi Geiger + speed test + 3D shooter (WebSocket)
//  Game: up to 640x480 @ 60 fps, auto quality (resolution drops first, then fps) - see GAME section
//  Board: ESP32 Dev Module / DOIT ESP32 DEVKIT V1     Libraries: "WebSockets" by Markus Sattler
//  Wiring: buzzer S -> GPIO 4, buzzer middle -> 3V3, buzzer - -> GND   (onboard LED = GPIO 2)
//  Save this text as an .ino sketch (File > New Sketch, paste, Save), then Upload.
// =====================================================================================
#pragma GCC optimize ("O3")
#include <WiFi.h>
#include <WebServer.h>
#include <WebSocketsServer.h>
#include <ESPmDNS.h>
#include <esp_wifi.h>
#include <math.h>

// ---------------- YOUR SETTINGS ----------------
const char* WIFI_SSID = "inet";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";      // <-- type your Wi-Fi password here

const int BUZ = 4;                // buzzer signal pin, HIGH = sound
const int LEDPIN = 2;             // onboard LED

// Geiger / percent calibration.
// RSSI_NEAR = signal when the ESP32 is RIGHT BESIDE the router. 100 % and the fastest clicks happen here.
// If 100 % shows too early, raise it (e.g. -28). If you never reach 100 % even at the router, lower it (e.g. -38).
const float RSSI_NEAR = -32.0f;
const float RSSI_FLOOR = -90.0f;  // 0 %
const float GEIGER_MAX_CPS = 12.5f;   // clicks per second at RSSI_NEAR (80 ms apart, same as before)
const float GEIGER_MIN_CPS = 0.25f;   // slowest click rate
const float GEIGER_DB_FACTOR = 0.85f; // each dB below RSSI_NEAR makes clicks 15 % slower (lower = steeper)

WebServer server(80);
bool buzzerOn = false;

// ---------------- Geiger shared state (used by json()) ----------------
bool geigerOn = false;
float gEma = -70.0f;
bool gHave = false;

// ---------------- RSSI sampling for the main page ----------------
const int N = 50;                 // 50 samples x 100 ms = 5 s window
int8_t buf[N];
int count = 0, head = 0;
unsigned long lastSample = 0;

void addSample(int r) {
  buf[head] = r; head = (head + 1) % N; if (count < N) count++;
}

float pctOf(float r) {
  float p = (r - RSSI_FLOOR) / (RSSI_NEAR - RSSI_FLOOR) * 100.0f;
  return p < 0 ? 0 : (p > 100 ? 100 : p);
}

String json() {
  bool conn = WiFi.status() == WL_CONNECTED;
  float mean = -90;
  if (count) { mean = 0; for (int i = 0; i < count; i++) mean += buf[i]; mean /= count; }
  if (geigerOn && gHave) mean = gEma;           // precise sniffed value while Geiger is on
  int8_t txq = 0; esp_wifi_get_max_tx_power(&txq);
  String s = "{";
  s += "\"conn\":" + String(conn ? "true" : "false");
  s += ",\"raw\":" + String(conn ? WiFi.RSSI() : 0);
  s += ",\"avg\":" + String(mean, 1);
  s += ",\"pct\":" + String((int)lroundf(pctOf(mean)));
  s += ",\"ssid\":\"" + WiFi.SSID() + "\"";
  s += ",\"ch\":" + String(WiFi.channel());
  s += ",\"tx\":" + String(txq / 4.0f, 1);
  s += "}";
  return s;
}

// ---------------- MAIN PAGE ----------------
const char PAGE[] PROGMEM = R"HTML(<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>ESP32 Wi-Fi</title>
<style>
body{font-family:sans-serif;max-width:420px;margin:28px auto;padding:0 16px;background:#111;color:#eee;text-align:center}
.word{font-size:46px;font-weight:bold;margin:12px 0 4px}
.sub{font-size:22px;color:#ccc}
.bar{height:24px;background:#333;border-radius:12px;overflow:hidden;margin:20px 0 8px}
.fill{height:100%;width:0;background:#0a7;transition:width .3s,background .3s}
.small{color:#888;font-size:13px}
a{display:inline-block;padding:14px 22px;margin:14px 5px 0;background:#0a7;color:#fff;border-radius:8px;text-decoration:none;font-size:17px}
</style></head><body>
<div class='small' id='net'>&nbsp;</div>
<div class='word' id='word'>...</div>
<div class='sub' id='sub'>connecting</div>
<div class='bar'><div class='fill' id='fill'></div></div>
<div class='small'>100 % only right beside the router. Distance is a rough estimate; walls change it.</div>
<a href='#' onclick="fetch('/on');return false">Buzzer ON</a><a href='#' onclick="fetch('/off');return false">Buzzer OFF</a><br>
<a href='/speed' style='background:#36c'>Speed test</a><a href='/game' style='background:#c33'>Play game</a><a href='#' onclick="fetch('/geiger').then(r=>r.text()).then(t=>this.textContent='Wi-Fi Geiger: '+t);return false" style='background:#639'>Wi-Fi Geiger</a>
<script>
function lvl(r){return r>-40?['Excellent','#0a7']:r>-50?['Good','#3b3']:r>-60?['Fair','#cb2']:r>-70?['Weak','#e82']:['Very weak','#d33']}
async function tick(){try{const d=await (await fetch('/data')).json();
 if(!d.conn){document.getElementById('word').textContent='No Wi-Fi';document.getElementById('sub').textContent='ESP32 lost the router';return}
 const l=lvl(d.avg),m=Math.pow(10,(-35-d.avg)/33),ms=m<10?m.toFixed(1):Math.round(m);
 document.getElementById('net').textContent=d.ssid+' | channel '+d.ch+' | TX '+d.tx+' dBm';
 const w=document.getElementById('word');w.textContent=l[0];w.style.color=l[1];
 document.getElementById('sub').textContent=d.avg.toFixed(1)+' dBm · '+d.pct+'% · ~'+ms+' m';
 const f=document.getElementById('fill');f.style.width=d.pct+'%';f.style.background=l[1];
}catch(e){document.getElementById('word').textContent='No response'}}
setInterval(tick,500);tick();
</script></body></html>)HTML";

// ---------------- SPEED TEST (phone <-> ESP32 Wi-Fi link) ----------------
const char SPEED[] PROGMEM = R"HTML(<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Speed test</title>
<style>
body{font-family:sans-serif;max-width:420px;margin:28px auto;padding:0 16px;background:#111;color:#eee;text-align:center}
.row{display:flex;justify-content:space-between;font-size:22px;padding:14px 4px;border-bottom:1px solid #333}
.row b{color:#0c9}
a,button{display:inline-block;padding:14px 26px;margin:20px 6px 0;background:#0a7;color:#fff;border:0;border-radius:8px;text-decoration:none;font-size:18px}
button:disabled{background:#555}
.small{color:#888;font-size:13px;margin-top:16px}
</style></head><body>
<h2>Wi-Fi speed test</h2>
<div class='row'><span>Ping</span><b id='ping'>-</b></div>
<div class='row'><span>Download</span><b id='dl'>-</b></div>
<div class='row'><span>Upload</span><b id='ul'>-</b></div>
<div id='st' class='small'>Press Start</div>
<button id='go' onclick='run()'>Start</button><a href='/'>Back</a>
<div class='small'>Measures the Wi-Fi link between this device and the ESP32, not your internet speed. The ESP32 itself limits it to a few Mbit/s.</div>
<script>
const $=id=>document.getElementById(id);
async function ping(){let t=[];for(let i=0;i<8;i++){const s=performance.now();await fetch('/ping',{cache:'no-store'});t.push(performance.now()-s)}
 t.sort((a,b)=>a-b);return t[Math.floor(t.length/2)]}
async function down(){let bytes=0;const s=performance.now();for(let i=0;i<3;i++){const b=await (await fetch('/dl?'+Math.random(),{cache:'no-store'})).arrayBuffer();bytes+=b.byteLength}
 return bytes*8/((performance.now()-s)/1000)/1e6}
async function up(){const blob=new Uint8Array(32768);let bytes=0;const s=performance.now();for(let i=0;i<10;i++){await fetch('/up',{method:'POST',body:blob,headers:{'Content-Type':'application/octet-stream'}});bytes+=blob.length}
 return bytes*8/((performance.now()-s)/1000)/1e6}
async function run(){const g=$('go');g.disabled=true;
 try{$('st').textContent='Testing ping...';$('ping').textContent=(await ping()).toFixed(0)+' ms';
 $('st').textContent='Testing download...';$('dl').textContent=(await down()).toFixed(1)+' Mbit/s';
 $('st').textContent='Testing upload...';$('ul').textContent=(await up()).toFixed(1)+' Mbit/s';
 $('st').textContent='Done'}catch(e){$('st').textContent='Test failed, try again'}
 g.disabled=false}
</script></body></html>)HTML";

void handleDownload() {
  const size_t total = 1024 * 1024;       // 1 MB per request
  static uint8_t chunk[1460];
  memset(chunk, 'A', sizeof(chunk));
  server.setContentLength(total);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/octet-stream", "");
  size_t sent = 0;
  while (sent < total) {
    size_t n = (total - sent) < sizeof(chunk) ? (total - sent) : sizeof(chunk);
    server.sendContent((const char*)chunk, n);
    sent += n;
  }
}

// =====================================================================================
//  3D GAME: all rendering happens on the ESP32 (ray casting + sprites), streamed to the phone
//
//  How it stays sharp AND fast over Wi-Fi:
//   * The picture is sent column by column as "runs" (how many pixels of one colour in a row).
//     A ray-cast picture is mostly long vertical strips, so a 640x480 frame is only ~4-7 KB
//     instead of 300 KB. At 60 fps that is ~2-3 Mbit/s, well inside what an ESP32 can push.
//   * Colour 0 means "sky / floor"; the phone paints it with a smooth gradient for that row.
//   * The ESP32 watches the Wi-Fi signal and how fast the phone answers each frame.
//     When things get worse it lowers the RESOLUTION first, and only then the FPS.
//     When things get better it gives back FPS first, then resolution.
// =====================================================================================
#define WMAX 640
#define HMAX 480
#define HDR 16                    // header bytes in front of every frame
#define OUT_MAX 36000             // frame buffer (normal frames are 3-8 KB)
const uint16_t QW[5] = {640, 480, 320, 240, 160};   // quality levels: 0 = best
const uint16_t QH[5] = {480, 360, 240, 180, 120};
const uint8_t FPSL[4] = {60, 45, 30, 20};             // fps levels: 0 = best

// '0' = empty, '1' = sand wall, '2' = stone wall, '3' = brick wall
const char* MAPSTR[16] = {
  "2222222222222222",
  "2000000000000002",
  "2000330000110002",
  "2000300000010002",
  "2000000110000002",
  "2030000000000302",
  "2030001001000302",
  "2000000000000002",
  "2000000000000002",
  "2030001001000302",
  "2030000000000302",
  "2000000110000002",
  "2000100000030002",
  "2000110000330002",
  "2000000000000002",
  "2222222222222222"
};
struct Enemy { float x, y; int hp; bool alive; float hitT, ph; };
Enemy en[8];
float px = 8.5f, py = 8.5f, pa = 0.0f;
float moveV = 0, turnV = 0, walkPh = 0, gTime = 0, deadT = 0;
int php = 100, pwave = 0, pscore = 0;
bool pdead = false;
float fireCd = 0, dmgCd = 0, flashT = 0, muzzleT = 0;
uint8_t col[HMAX];                // one screen column, rendered then compressed
uint8_t gout[HDR + OUT_MAX];

bool isWall(float x, float y) {
  int ix = (int)x, iy = (int)y;
  if (x < 0 || y < 0 || ix >= 16 || iy >= 16) return true;
  return MAPSTR[iy][ix] != '0';
}

void spawnWave() {
  pwave++;
  int n = pwave + 2;
  if (n > 8) n = 8;
  for (int i = 0; i < 8; i++) en[i].alive = false;
  for (int i = 0; i < n; i++) {
    float x = 1.5f, y = 1.5f;
    for (int t = 0; t < 60; t++) {
      float cx = random(1, 15) + 0.5f, cy = random(1, 15) + 0.5f;
      if (!isWall(cx, cy) && hypotf(cx - px, cy - py) > 6.0f) { x = cx; y = cy; break; }
    }
    en[i].x = x; en[i].y = y; en[i].hp = 2 + pwave / 3; en[i].alive = true; en[i].hitT = 0;
    en[i].ph = random(0, 628) / 100.0f;
  }
}

void resetGame() {
  px = 8.5f; py = 8.5f; pa = 0; php = 100; pwave = 0; pscore = 0; pdead = false;
  moveV = 0; turnV = 0; deadT = 0;
  fireCd = 0; dmgCd = 0; flashT = 0; muzzleT = 0;
  spawnWave();
}

float wallDistAhead() {
  float d = 0;
  while (d < 20 && !isWall(px + cosf(pa) * d, py + sinf(pa) * d)) d += 0.05f;
  return d;
}

void shoot() {
  float wd = wallDistAhead();
  int best = -1;
  float bestD = 99;
  for (int i = 0; i < 8; i++) {
    if (!en[i].alive) continue;
    float dx = en[i].x - px, dy = en[i].y - py;
    float d = hypotf(dx, dy);
    float ang = atan2f(dy, dx) - pa;
    while (ang > PI) ang -= 2 * PI;
    while (ang < -PI) ang += 2 * PI;
    if (d < wd && d < bestD && fabsf(ang) < 0.32f / d + 0.03f) { best = i; bestD = d; }
  }
  if (best >= 0) {
    en[best].hp--;
    en[best].hitT = 0.12f;
    if (en[best].hp <= 0) { en[best].alive = false; pscore += 100; }
  }
}

// Runs at a fixed 120 steps per second, so movement is equally smooth at any frame rate.
void gameUpdate(float dt, int k) {
  gTime += dt;
  if (pdead) { deadT += dt; if ((k & 16) && deadT > 1.0f) resetGame(); return; }
  // eased turning / walking: starts and stops quickly but without jerks
  float tTurn = ((k & 8) ? 2.6f : 0) - ((k & 4) ? 2.6f : 0);
  turnV += (tTurn - turnV) * fminf(1.0f, dt * 14.0f);
  pa += turnV * dt;
  float tSp = (k & 1) ? 3.2f : ((k & 2) ? -2.4f : 0);
  moveV += (tSp - moveV) * fminf(1.0f, dt * 10.0f);
  walkPh += fabsf(moveV) * dt * 3.2f;
  float dx = cosf(pa) * moveV * dt, dy = sinf(pa) * moveV * dt;
  if (!isWall(px + dx + (dx > 0 ? 0.2f : -0.2f), py)) px += dx;
  if (!isWall(px, py + dy + (dy > 0 ? 0.2f : -0.2f))) py += dy;
  fireCd -= dt; flashT -= dt; muzzleT -= dt; dmgCd -= dt;
  if ((k & 16) && fireCd <= 0) { fireCd = 0.28f; muzzleT = 0.08f; shoot(); }
  float spd = 0.9f + 0.12f * pwave;
  if (spd > 2.2f) spd = 2.2f;
  int alive = 0;
  for (int i = 0; i < 8; i++) {
    Enemy &e = en[i];
    if (!e.alive) continue;
    alive++;
    e.hitT -= dt;
    float ex = px - e.x, ey = py - e.y;
    float d = hypotf(ex, ey);
    if (d > 0.55f) {
      float st = spd * dt;
      float mx = ex / d * st, my = ey / d * st;
      if (!isWall(e.x + mx, e.y)) e.x += mx;
      if (!isWall(e.x, e.y + my)) e.y += my;
    } else if (dmgCd <= 0) {
      php -= 10; dmgCd = 0.45f; flashT = 0.2f;
      if (php <= 0) { php = 0; pdead = true; deadT = 0; }
    }
  }
  if (alive == 0) { pscore += 50; spawnWave(); }
}

// Colour numbers (the phone has the same table):
//   0 sky/floor, 1..144 walls (material*2+side)*24 + shade + 1, 150..165 enemy, 166..181 enemy shadow,
//   182 eye, 183 pupil, 184 hit flash, 190..193 gun, 194..195 muzzle flash, 196 crosshair
struct Spr { float ty; int left, sw, top, sh, shade; bool hit; };

size_t gameRender(int W, int H) {
  uint8_t* out = gout + HDR;
  uint8_t* const end = gout + HDR + OUT_MAX;
  auto fill = [&](int a, int b, uint8_t c) {
    if (a < 0) a = 0;
    if (b > H) b = H;
    if (a < b) memset(col + a, c, b - a);
  };
  float dirX = cosf(pa), dirY = sinf(pa);
  float plX = -dirY * 0.66f, plY = dirX * 0.66f;

  // enemies -> screen rectangles, sorted far to near
  Spr sp[8];
  int ns = 0;
  float invDet = 1.0f / (plX * dirY - dirX * plY);
  for (int i = 0; i < 8; i++) {
    Enemy &e = en[i];
    if (!e.alive) continue;
    float sx = e.x - px, sy = e.y - py;
    float tx = invDet * (dirY * sx - dirX * sy);
    float ty = invDet * (-plY * sx + plX * sy);
    if (ty < 0.15f) continue;
    Spr s;
    s.sh = (int)(H / ty * 0.75f);
    if (s.sh > H * 3) s.sh = H * 3;
    if (s.sh < 2) s.sh = 2;
    s.sw = (int)(s.sh * 0.7f);
    if (s.sw < 1) s.sw = 1;
    int scr = (int)((W / 2) * (1.0f + tx / ty));
    s.top = H / 2 - s.sh / 2 + (int)(s.sh * (0.12f + 0.05f * sinf(gTime * 4.0f + e.ph)));
    s.left = scr - s.sw / 2;
    s.shade = (int)(ty * 1.4f);
    if (s.shade > 15) s.shade = 15;
    s.hit = e.hitT > 0;
    s.ty = ty;
    int j = ns - 1;
    while (j >= 0 && sp[j].ty < ty) { sp[j + 1] = sp[j]; j--; }
    sp[j + 1] = s;
    ns++;
  }

  // gun (bobs while walking, kicks back when firing), muzzle flash, crosshair
  int rec = muzzleT > 0 ? (int)(H * 0.035f) : 0;
  int gby = (int)(fabsf(cosf(walkPh)) * H * 0.025f) + rec;
  int gcx = W / 2 + (int)(sinf(walkPh) * W * 0.014f);
  int gTop = H - (int)(H * 0.24f) + gby;
  int bHalf = (int)(W * 0.035f); if (bHalf < 2) bHalf = 2;
  int gripHalf = (int)(W * 0.10f);
  int gripTop = H - (int)(H * 0.09f) + gby;
  int capH = (int)(H * 0.02f) + 1;
  bool flash = muzzleT > 0;
  int fcy = gTop - (int)(H * 0.05f), frx = (int)(W * 0.05f) + 1, fry = (int)(H * 0.065f) + 1;
  int cx = W / 2, cy = H / 2, cg = H / 90 + 1, cl = H / 36 + 2, ct = H >= 360 ? 2 : 1;

  for (int x = 0; x < W; x++) {
    // ---- ray cast this column ----
    float camX = 2.0f * x / W - 1.0f;
    float rx = dirX + plX * camX, ry = dirY + plY * camX;
    int mx = (int)px, my = (int)py;
    float ddx = rx == 0 ? 1e30f : fabsf(1.0f / rx);
    float ddy = ry == 0 ? 1e30f : fabsf(1.0f / ry);
    int stx, sty;
    float sdx, sdy;
    if (rx < 0) { stx = -1; sdx = (px - mx) * ddx; } else { stx = 1; sdx = (mx + 1.0f - px) * ddx; }
    if (ry < 0) { sty = -1; sdy = (py - my) * ddy; } else { sty = 1; sdy = (my + 1.0f - py) * ddy; }
    int side = 0, mat = 1;
    for (int i = 0; i < 40; i++) {
      if (sdx < sdy) { sdx += ddx; mx += stx; side = 0; } else { sdy += ddy; my += sty; side = 1; }
      if (mx < 0 || my < 0 || mx > 15 || my > 15) break;
      char ch = MAPSTR[my][mx];
      if (ch != '0') { mat = ch - '1'; break; }
    }
    if (mat < 0 || mat > 2) mat = 1;
    float perp = side == 0 ? sdx - ddx : sdy - ddy;
    if (perp < 0.05f) perp = 0.05f;
    int lh = (int)(H / perp);
    int y0 = H / 2 - lh / 2;
    float wx = side == 0 ? py + perp * ry : px + perp * rx;
    wx -= floorf(wx);
    int k = (int)(perp * 2.2f);
    if (wx < 0.035f || wx > 0.965f) k += 4;      // dark seam between wall blocks
    if (k > 23) k = 23;
    memset(col, 0, H);
    fill(y0, y0 + lh, 1 + (mat * 2 + side) * 24 + k);

    // ---- enemies in this column (far ones first, near ones paint over) ----
    for (int n = 0; n < ns; n++) {
      Spr &s = sp[n];
      if (x < s.left || x >= s.left + s.sw || s.ty >= perp) continue;
      float u = (x - s.left + 0.5f) / s.sw;
      float du = u * 2 - 1;
      float hh = sqrtf(fmaxf(0.0f, 1.0f - du * du));    // oval body
      int ya = s.top + (int)(s.sh * (0.5f - 0.5f * hh));
      int yb = s.top + (int)(s.sh * (0.5f + 0.5f * hh));
      if (s.hit) { fill(ya, yb, 184); continue; }
      int mid = s.top + (int)(s.sh * 0.64f);
      if (mid < ya) mid = ya;
      if (mid > yb) mid = yb;
      fill(ya, mid, 150 + s.shade);
      fill(mid, yb, 166 + s.shade);
      bool eL = u > 0.22f && u < 0.40f, eR = u > 0.60f && u < 0.78f;
      if (eL || eR) {
        int e0 = max(ya, s.top + (int)(s.sh * 0.27f)), e1 = min(yb, s.top + (int)(s.sh * 0.41f));
        fill(e0, e1, 182);
        if (fabsf(u - (eL ? 0.31f : 0.69f)) < 0.045f)
          fill(max(e0, s.top + (int)(s.sh * 0.32f)), min(e1, s.top + (int)(s.sh * 0.40f)), 183);
      }
    }

    // ---- crosshair ----
    if (x > cx - ct && x <= cx) { fill(cy - cg - cl, cy - cg, 196); fill(cy + cg + 1, cy + cg + cl + 1, 196); }
    if ((x >= cx - cg - cl && x < cx - cg) || (x > cx + cg && x <= cx + cg + cl)) fill(cy - ct + 1, cy + 1, 196);

    // ---- muzzle flash ----
    int fdx = x - gcx;
    if (flash && fdx > -frx && fdx < frx) {
      float t = (float)fdx / frx;
      int h = (int)(fry * sqrtf(1.0f - t * t));
      fill(fcy - h, fcy + h, 195);
      if (fabsf(t) < 0.5f) { int h2 = (int)(fry * 0.5f * sqrtf(1.0f - 4 * t * t)); fill(fcy - h2, fcy + h2, 194); }
    }

    // ---- gun: hands/grip, then barrel ----
    if (fdx >= -gripHalf && fdx <= gripHalf) {
      float t = (float)fdx / gripHalf;
      fill(gripTop + (int)(H * 0.04f * t * t), H, 193);
    }
    if (fdx >= -bHalf && fdx <= bHalf) {
      float rel = (float)(fdx + bHalf) / (2 * bHalf + 1);
      fill(gTop, H, rel < 0.25f ? 190 : (rel > 0.72f ? 192 : 191));
      fill(gTop, gTop + capH, 193);
    }

    // ---- compress this column into runs: [length, colour] ----
    int colsLeft = W - 1 - x;
    if (end - out - colsLeft * 4 < 2 * H + 4) {     // safety net, never hit in normal play
      uint8_t c = col[H / 2];
      int n = H;
      while (n > 255) { *out++ = 255; *out++ = c; n -= 255; }
      *out++ = n; *out++ = c;
      continue;
    }
    int y = 0;
    while (y < H) {
      uint8_t c = col[y];
      int y2 = y + 1;
      while (y2 < H && col[y2] == c) y2++;
      int n = y2 - y;
      while (n > 255) { *out++ = 255; *out++ = c; n -= 255; }
      *out++ = n; *out++ = c;
      y = y2;
    }
  }
  return out - (gout + HDR);
}

// ---------------- WebSocket stream: ESP32 renders, pushes frames to the phone ----------------
// Small helper so we can switch off Nagle's delay on the game socket (frames leave instantly).
class GameWS : public WebSocketsServer {
 public:
  GameWS(uint16_t port) : WebSocketsServer(port) {}
  void noDelay(uint8_t n) {
    if (n < WEBSOCKETS_SERVER_CLIENT_MAX && _clients[n].tcp) _clients[n].tcp->setNoDelay(true);
  }
};
GameWS ws(81);
volatile uint8_t wsKeys = 0, wsManual = 0;      // wsManual: 0 = auto quality, 1..5 = fixed level
int wsInflight = 0;                             // frames sent but not yet confirmed by the phone
bool wsActive = false;
uint8_t wsClient = 0;
const int MAX_INFLIGHT = 3;
uint32_t sendT[4];
uint8_t sendHead = 0;
uint32_t lastAckUs = 0;
const uint32_t PHYS_US = 8333;                  // 120 game steps per second
uint32_t physT = 0, nextFrameUs = 0, adaptT = 0;

// link quality bookkeeping (reset every 0.5 s)
uint32_t stDue = 0, stSkip = 0, stSent = 0, stAck = 0, stRttUs = 0, stSendUs = 0;
uint8_t qLvl = 1, fLvl = 0, rssiCap = 0, rttShown = 0;
int goodN = 0, upHold = 6, sinceUp = 999, sinceBad = 0;
float rssiEma = -60.0f;

void wsEvent(uint8_t num, WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_CONNECTED) {
    wsClient = num; wsActive = true; wsInflight = 0; wsKeys = 0;
    ws.noDelay(num);
    physT = nextFrameUs = adaptT = micros();
    qLvl = max(1, (int)rssiCap); fLvl = 0; goodN = 0; upHold = 6; sinceUp = 999;
  } else if (type == WStype_DISCONNECTED) {
    if (num == wsClient) { wsActive = false; wsKeys = 0; }
  } else if (type == WStype_BIN && length >= 1 && num == wsClient) {
    wsKeys = payload[0];
    if (length > 2) wsManual = payload[2] > 5 ? 0 : payload[2];
    if (length > 1 && payload[1] && wsInflight > 0) {         // 2nd byte = "frame received"
      uint32_t now = micros();
      stRttUs += now - sendT[(uint8_t)(sendHead - wsInflight) & 3];
      stAck++;
      wsInflight--;
      lastAckUs = now;
    }
  }
}

// Every 0.5 s: decide the quality level and fps level.
// Worse link -> lower resolution first, then lower fps. Better link -> fps back first, then resolution.
void adapt() {
  static const int8_t T[4] = {-62, -68, -74, -80};     // signal steps (ESP32 <-> router, dBm)
  int c = 0;
  for (int i = 0; i < 4; i++) if (rssiEma < T[i]) c = i + 1;
  if (c > rssiCap || (c < rssiCap && rssiEma > T[rssiCap - 1] + 3)) rssiCap = c;   // 3 dB hysteresis

  float per = 1000.0f / FPSL[fLvl];
  float skip = stDue ? (float)stSkip / stDue : 0;
  float rtt = stAck ? stRttUs / 1000.0f / stAck : 0;
  float snd = stSent ? stSendUs / 1000.0f / stSent : 0;
  rttShown = rtt > 255 ? 255 : (uint8_t)rtt;
  stDue = stSkip = stSent = stAck = stRttUs = stSendUs = 0;

  if (wsManual) { qLvl = wsManual - 1; fLvl = 0; return; }

  bool bad = skip > 0.08f || rtt > per * 2.5f + 10 || snd > per * 0.5f;
  bool good = skip == 0 && rtt < per * 1.3f + 5 && snd < per * 0.25f;
  sinceUp++;
  if (bad) {
    goodN = 0; sinceBad = 0;
    if (sinceUp < 8) upHold = min(upHold * 2, 64);   // the last step up was too much: wait longer next time
    if (qLvl < 4) qLvl++;
    else if (fLvl < 3) fLvl++;
  } else {
    if (++sinceBad > 60) upHold = 6;                 // 30 s without trouble: be quick to upgrade again
    if (!good) goodN = 0;
    else if (++goodN >= upHold) {
      goodN = 0;
      if (fLvl > 0) { fLvl--; sinceUp = 0; }
      else if (qLvl > rssiCap) { qLvl--; sinceUp = 0; }
    }
  }
  if (qLvl < rssiCap) qLvl = rssiCap;                // weak signal: drop resolution right away, keep fps
}

void gameStream() {
  if (!wsActive) return;
  uint32_t now = micros();
  if (now - physT > 200000) physT = now - PHYS_US;   // long hiccup: don't fast-forward the game
  while ((int32_t)(now - physT) >= (int32_t)PHYS_US) { gameUpdate(PHYS_US / 1000000.0f, wsKeys); physT += PHYS_US; }
  if (now - adaptT >= 500000) { adaptT = now; adapt(); }

  // frames leave on an exact, even beat (16.7 ms at 60 fps) - this is what makes it look smooth
  if ((int32_t)(now - nextFrameUs) < 0) return;
  uint32_t period = 1000000UL / FPSL[fLvl];
  nextFrameUs += period;
  if ((int32_t)(now - nextFrameUs) > 0) nextFrameUs = now + period;
  stDue++;
  if (wsInflight >= MAX_INFLIGHT) {
    if (now - lastAckUs < 400000) { stSkip++; return; }   // phone/Wi-Fi is behind: skip this frame
    wsInflight = 0;                                      // phone stalled: recover
  }

  int W = QW[qLvl], H = QH[qLvl];
  uint32_t t0 = micros();
  size_t n = gameRender(W, H);
  uint32_t rt = (micros() - t0) / 100;                // render time in 0.1 ms

  static uint32_t fpsT = 0;
  static int fpsN = 0;
  static uint8_t fpsShown = 0;
  fpsN++;
  if (now - fpsT >= 1000000) { fpsShown = fpsN > 255 ? 255 : fpsN; fpsN = 0; fpsT = now; }

  int alive = 0;
  for (int i = 0; i < 8; i++) if (en[i].alive) alive++;
  gout[0] = php; gout[1] = pwave; gout[2] = pscore & 255; gout[3] = (pscore >> 8) & 255;
  gout[4] = (flashT > 0 ? 1 : 0) | (pdead ? 2 : 0) | (muzzleT > 0 ? 4 : 0);
  gout[5] = alive;
  gout[6] = rt > 255 ? 255 : rt;
  gout[7] = fpsShown;
  gout[8] = W & 255; gout[9] = W >> 8; gout[10] = H & 255; gout[11] = H >> 8;
  gout[12] = qLvl | (fLvl << 4) | (wsManual ? 0x80 : 0);
  gout[13] = FPSL[fLvl];
  gout[14] = (uint8_t)(-(int)rssiEma);
  gout[15] = rttShown;

  uint32_t t1 = micros();
  ws.sendBIN(wsClient, gout, HDR + n);
  stSendUs += micros() - t1;
  stSent++;
  if (wsInflight == 0) lastAckUs = t1;
  sendT[sendHead & 3] = t1;
  sendHead++;
  wsInflight++;
}

const char GAME[] PROGMEM = R"HTML(<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover'>
<meta name='apple-mobile-web-app-capable' content='yes'><meta name='apple-mobile-web-app-status-bar-style' content='black-translucent'>
<meta name='theme-color' content='#07080c'><title>ESP32 Shooter</title>
<style>
:root{--bg:#07080c;--line:#2a2e3a;--txt:#eef0f5;--dim:#8a90a0;--acc:#3ddc97}
html,body{margin:0;height:100%;background:var(--bg);color:var(--txt);font-family:-apple-system,system-ui,sans-serif;overflow:hidden;touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none;-webkit-tap-highlight-color:transparent;overscroll-behavior:none}
#app{position:relative;height:100vh;height:100dvh;display:flex;flex-direction:column;box-sizing:border-box;padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}
#view{position:relative;width:100%;aspect-ratio:4/3;background:#000;overflow:hidden;flex:none}
canvas{width:100%;height:100%;display:block}
#hud{position:absolute;left:0;right:0;top:0;display:flex;align-items:center;gap:10px;padding:8px 10px;font-weight:700;font-size:15px;text-shadow:0 1px 3px #000,0 0 6px #000;pointer-events:none}
#back{pointer-events:auto;width:30px;height:30px;border-radius:15px;background:rgba(0,0,0,.45);color:#fff;text-decoration:none;display:flex;align-items:center;justify-content:center;font-size:20px;line-height:1}
#wv{flex:1;text-align:center;font-weight:600;font-size:14px}
#fps{color:var(--acc);min-width:54px;text-align:right}
#hpw{position:absolute;left:10px;right:10px;bottom:8px;height:7px;border-radius:4px;background:rgba(0,0,0,.55);overflow:hidden;pointer-events:none}
#hpf{height:100%;width:100%;background:linear-gradient(90deg,#e5484d,#ff7a6b);transition:width .15s}
#flash{position:absolute;inset:0;background:radial-gradient(transparent 40%,rgba(255,0,0,.55));opacity:0;pointer-events:none;transition:opacity .15s}
#over{position:absolute;inset:0;display:none;align-items:center;justify-content:center;flex-direction:column;background:rgba(0,0,0,.6);font-size:30px;font-weight:800}
#over small{font-size:15px;font-weight:500;margin-top:8px;color:#ccc}
#bar{display:flex;align-items:center;gap:8px;padding:8px 12px;font-size:12px;color:var(--dim);flex:none}
#st{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
#qb{flex:none;font:600 12px -apple-system,system-ui,sans-serif;color:var(--acc);background:rgba(61,220,151,.12);border:1px solid rgba(61,220,151,.35);border-radius:12px;padding:4px 10px}
#ctl{flex:1;min-height:0;display:flex;align-items:center;justify-content:space-between;padding:6px 22px 14px}
#pad{position:relative;width:min(48vw,200px);aspect-ratio:1;border-radius:50%;background:radial-gradient(circle,#1d2029 0,#14161d 70%);border:2px solid var(--line);box-shadow:inset 0 2px 10px rgba(0,0,0,.6);touch-action:none}
.ar{position:absolute;width:0;height:0;border:13px solid transparent;opacity:.75}
.u{left:50%;top:10%;margin-left:-13px;border-bottom:20px solid #cfd3dc;border-top:0}
.d{left:50%;bottom:10%;margin-left:-13px;border-top:20px solid #cfd3dc;border-bottom:0}
.l{top:50%;left:10%;margin-top:-13px;border-right:20px solid #cfd3dc;border-left:0}
.r{top:50%;right:10%;margin-top:-13px;border-left:20px solid #cfd3dc;border-right:0}
.u.on{border-bottom-color:var(--acc);opacity:1}.d.on{border-top-color:var(--acc);opacity:1}.l.on{border-right-color:var(--acc);opacity:1}.r.on{border-left-color:var(--acc);opacity:1}
#knob{position:absolute;left:50%;top:50%;width:34%;height:34%;margin:-17% 0 0 -17%;border-radius:50%;background:radial-gradient(circle at 40% 35%,#4a4f5e,#2a2e3a);border:1px solid #555b6b;pointer-events:none;transition:transform .08s}
#fire{width:min(38vw,150px);aspect-ratio:1;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:22px;letter-spacing:1px;background:radial-gradient(circle at 38% 32%,#f2685f,#b01b22 70%);box-shadow:0 6px 0 #5e0d10,0 0 0 5px rgba(229,72,77,.18);touch-action:none}
#fire.on{transform:translateY(4px);box-shadow:0 2px 0 #5e0d10,0 0 0 8px rgba(229,72,77,.3)}
@media (orientation:landscape){
 #app{flex-direction:row;justify-content:center;align-items:center}
 #view{height:100%;width:auto;max-width:62vw}
 #bar{position:absolute;left:50%;bottom:calc(env(safe-area-inset-bottom) + 2px);transform:translateX(-50%);padding:2px 8px;background:rgba(0,0,0,.55);border-radius:10px;max-width:60vw}
 #ctl{position:absolute;inset:0;padding:0 calc(env(safe-area-inset-right) + 14px) 0 calc(env(safe-area-inset-left) + 14px);pointer-events:none}
 #pad,#fire{pointer-events:auto}
 #pad{width:min(19vw,170px)}#fire{width:min(14vw,120px)}
}
</style></head><body>
<div id='app'>
 <div id='view'><canvas id='c' width='320' height='240'></canvas>
  <div id='hud'><a id='back' href='/'>&lsaquo;</a><span id='sc'>0</span><span id='wv'>Wave 1</span><span id='fps'>--</span></div>
  <div id='hpw'><div id='hpf'></div></div>
  <div id='flash'></div>
  <div id='over'>GAME OVER<small>Press FIRE to restart</small></div></div>
 <div id='bar'><span id='st'>connecting...</span><button id='qb'>AUTO</button></div>
 <div id='ctl'>
  <div id='pad'><div class='ar u'></div><div class='ar d'></div><div class='ar l'></div><div class='ar r'></div><div id='knob'></div></div>
  <div id='fire'>FIRE</div></div>
</div>
<script>
const $=id=>document.getElementById(id),c=$('c'),g=c.getContext('2d',{alpha:false});
// ---- colour table (same numbers as the ESP32) ----
const rgb=(r,gg,b)=>(255<<24)|((b|0)<<16)|((gg|0)<<8)|(r|0);
const mix=(a,b,t)=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t];
const PAL=new Uint32Array(256),FOG=[24,24,36];
[[214,172,112],[140,152,176],[178,86,64]].forEach((m,mi)=>{for(let s=0;s<2;s++)for(let k=0;k<24;k++){
 const b=m.map(v=>v*(s?0.72:1));PAL[1+(mi*2+s)*24+k]=rgb(...mix(b,FOG,Math.pow(k/23,0.8)*0.9))}});
for(let k=0;k<16;k++){const t=Math.pow(k/15,0.8)*0.85;PAL[150+k]=rgb(...mix([238,64,62],FOG,t));PAL[166+k]=rgb(...mix([150,30,42],FOG,t))}
PAL[182]=rgb(255,226,90);PAL[183]=rgb(30,8,10);PAL[184]=rgb(255,255,255);
PAL[190]=rgb(158,164,180);PAL[191]=rgb(98,102,118);PAL[192]=rgb(56,58,70);PAL[193]=rgb(30,31,38);
PAL[194]=rgb(255,250,215);PAL[195]=rgb(255,170,50);PAL[196]=rgb(255,245,170);
let W=0,H=0,img,px,bg;
function resize(w,h){W=w;H=h;c.width=w;c.height=h;img=g.createImageData(w,h);px=new Uint32Array(img.data.buffer);bg=new Uint32Array(h);
 const hz=h/2;for(let y=0;y<h;y++){if(y<hz){const t=y/hz;bg[y]=rgb(...mix([6,8,24],[50,44,82],t*t))}else{const t=(y-hz)/hz;bg[y]=rgb(...mix(FOG,[100,100,110],Math.sqrt(t)))}}
 c.style.imageRendering=w>=480?'auto':'pixelated'}
// ---- unpack one frame: per column, pairs of [length, colour] ----
function decode(b){const w=b[8]|b[9]<<8,h=b[10]|b[11]<<8;if(w!==W||h!==H)resize(w,h);
 const n=b.length;let p=16;
 for(let x=0;x<w;x++){let y=0,i=x;
  while(y<h&&p<n){let len=b[p++];const ci=b[p++];let e=y+len;if(e>h)e=h;
   if(ci===0){for(;y<e;y++,i+=w)px[i]=bg[y]}else{const v=PAL[ci];for(;y<e;y++,i+=w)px[i]=v}}}
 g.putImageData(img,0,0)}
// ---- network ----
let ws=null,keys=0,manual=0,queue=[],bytes=0,frames=0,t0=performance.now(),lastHud=0,last=null;
function send(ack){if(ws&&ws.readyState===1)ws.send(Uint8Array.of(keys,ack,manual))}
function conn(){ws=new WebSocket('ws://'+location.hostname+':81');ws.binaryType='arraybuffer';
 ws.onmessage=e=>{queue.push(new Uint8Array(e.data));bytes+=e.data.byteLength;send(1)};
 ws.onopen=()=>send(0);
 ws.onclose=()=>{$('st').textContent='reconnecting...';setTimeout(conn,500)}}
conn();
// ---- show frames on the screen refresh (with a 1-frame cushion against Wi-Fi jitter) ----
function loop(){requestAnimationFrame(loop);
 if(!queue.length)return;
 if(queue.length>2)queue=queue.slice(-1);
 const b=queue.shift();decode(b);last=b;frames++;
 const now=performance.now();
 if(now-t0>=500){const s=(now-t0)/1000,f=Math.round(frames/s),kb=bytes/frames/1024,mb=bytes*8/s/1e6;frames=0;bytes=0;t0=now;
  $('fps').textContent=f+' fps';
  $('st').textContent=W+'×'+H+' · '+b[13]+' fps · '+kb.toFixed(1)+' KB/frame · '+mb.toFixed(1)+' Mbit/s · Wi-Fi -'+b[14]+' dBm · '+b[15]+' ms · render '+(b[6]/10).toFixed(1)+' ms';
  $('qb').textContent=manual?('FIXED '+W+'p'):('AUTO '+H+'p')}
 if(now-lastHud>80){lastHud=now;
  $('hpf').style.width=b[0]+'%';$('sc').textContent=(b[2]|(b[3]<<8));$('wv').textContent='Wave '+b[1]+' · '+b[5]+' left';
  $('flash').style.opacity=(b[4]&1)?1:0;$('over').style.display=(b[4]&2)?'flex':'none'}}
requestAnimationFrame(loop);
// ---- controls ----
['gesturestart','gesturechange','gestureend','dblclick','contextmenu'].forEach(n=>document.addEventListener(n,e=>e.preventDefault()));
document.addEventListener('touchmove',e=>e.preventDefault(),{passive:false});
document.addEventListener('touchend',e=>{if(e.target.closest('#pad,#fire'))e.preventDefault()},{passive:false});
function setKeys(n){if(n!==keys){keys=n;send(0)}}
const pad=$('pad'),knob=$('knob'),AR={1:pad.querySelector('.u'),2:pad.querySelector('.d'),4:pad.querySelector('.l'),8:pad.querySelector('.r')};
let padId=null;
function padDir(d){setKeys((keys&16)|d);for(const k in AR)AR[k].classList.toggle('on',!!(d&k))}
function padMove(e){const r=pad.getBoundingClientRect(),R=r.width/2;let dx=e.clientX-r.left-R,dy=e.clientY-r.top-R;const d=Math.hypot(dx,dy);let k=0;
 if(d>R*0.18){const a=Math.atan2(dy,dx)*57.3;if(a>-67.5&&a<67.5)k|=8;if(a>112.5||a<-112.5)k|=4;if(a>22.5&&a<157.5)k|=2;if(a<-22.5&&a>-157.5)k|=1}
 const m=R*0.55;if(d>m){dx*=m/d;dy*=m/d}knob.style.transform='translate('+dx+'px,'+dy+'px)';padDir(k)}
pad.addEventListener('pointerdown',e=>{e.preventDefault();padId=e.pointerId;pad.setPointerCapture(e.pointerId);knob.style.transition='none';padMove(e)});
pad.addEventListener('pointermove',e=>{if(e.pointerId===padId)padMove(e)});
['pointerup','pointercancel','lostpointercapture'].forEach(n=>pad.addEventListener(n,e=>{if(e.pointerId===padId){padId=null;knob.style.transition='';knob.style.transform='';padDir(0)}}));
const fire=$('fire');
fire.addEventListener('pointerdown',e=>{e.preventDefault();fire.setPointerCapture(e.pointerId);fire.classList.add('on');setKeys(keys|16)});
['pointerup','pointercancel','lostpointercapture'].forEach(n=>fire.addEventListener(n,()=>{fire.classList.remove('on');setKeys(keys&~16)}));
$('qb').addEventListener('click',()=>{manual=(manual+1)%6;send(0);$('qb').textContent=manual?'FIXED...':'AUTO'});
const km={ArrowUp:1,w:1,ArrowDown:2,s:2,ArrowLeft:4,a:4,ArrowRight:8,d:8,' ':16};
addEventListener('keydown',e=>{if(km[e.key]){setKeys(keys|km[e.key]);e.preventDefault()}});
addEventListener('keyup',e=>{if(km[e.key])setKeys(keys&~km[e.key])});
</script></body></html>)HTML";

// =====================================================================================
//  Wi-Fi GEIGER: sniffs every router frame for precise RSSI. Fast clicks ONLY right beside the router.
// =====================================================================================
unsigned long geigerNext = 0, geigerOffAt = 0, udpNext = 0;
uint8_t rtrMac[6];
volatile int8_t sn[16];
volatile uint8_t snHead = 0;
volatile uint32_t snCount = 0;
uint32_t snLast = 0;
WiFiUDP gUdp;

void sniffCb(void* buf, wifi_promiscuous_pkt_type_t type) {
  if (type != WIFI_PKT_MGMT && type != WIFI_PKT_DATA) return;
  const wifi_promiscuous_pkt_t* p = (const wifi_promiscuous_pkt_t*)buf;
  const uint8_t* a = p->payload + 10;             // transmitter address of the frame
  for (int i = 0; i < 6; i++) if (a[i] != rtrMac[i]) return;
  sn[snHead] = p->rx_ctrl.rssi;
  snHead = (snHead + 1) & 15;
  snCount++;
}

void sniffStart() {
  memcpy(rtrMac, WiFi.BSSID(), 6);
  snCount = 0; snLast = 0; gHave = false;
  wifi_promiscuous_filter_t f;
  f.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT | WIFI_PROMIS_FILTER_MASK_DATA;
  esp_wifi_set_promiscuous_filter(&f);
  esp_wifi_set_promiscuous_rx_cb(&sniffCb);
  esp_wifi_set_promiscuous(true);
}

void sniffStop() { esp_wifi_set_promiscuous(false); }

float sniffRssi() {
  uint32_t c = snCount;
  if (c != snLast && c > 0) {
    snLast = c;
    int n = c < 16 ? (int)c : 16;
    int8_t t[16];
    for (int i = 0; i < n; i++) t[i] = sn[i];
    for (int i = 1; i < n; i++) { int8_t k = t[i]; int j = i - 1; while (j >= 0 && t[j] > k) { t[j + 1] = t[j]; j--; } t[j + 1] = k; }
    int trim = n >= 8 ? n / 4 : 0;                 // drop the highest and lowest quarter
    float s = 0;
    for (int i = trim; i < n - trim; i++) s += t[i];
    float m = s / (n - 2 * trim);
    if (!gHave) { gEma = m; gHave = true; } else gEma += 0.3f * (m - gEma);
  }
  return gEma;
}

void geigerTick() {
  unsigned long now = millis();
  if (geigerOffAt && now >= geigerOffAt) {
    digitalWrite(BUZ, LOW);
    digitalWrite(LEDPIN, LOW);
    geigerOffAt = 0;
  }
  if (!geigerOn) return;
  if (now >= udpNext) {                           // poke the router so it answers: more frames = more samples
    udpNext = now + 25;
    gUdp.beginPacket(WiFi.gatewayIP(), 9);
    gUdp.write((const uint8_t*)"x", 1);
    gUdp.endPacket();
  }
  float r = sniffRssi();
  if (now < geigerNext) return;
  float below = RSSI_NEAR - r;                    // dB weaker than "right beside the router"
  float rate = GEIGER_MAX_CPS;
  if (below > 0) rate = GEIGER_MAX_CPS * powf(GEIGER_DB_FACTOR, below);
  if (rate < GEIGER_MIN_CPS) rate = GEIGER_MIN_CPS;
  geigerNext = now + (unsigned long)(1000.0f / rate);
  digitalWrite(BUZ, HIGH);
  digitalWrite(LEDPIN, HIGH);
  geigerOffAt = now + 20;
}

void handleGeiger() {
  geigerOn = !geigerOn;
  if (geigerOn) {
    sniffStart();
  } else {
    sniffStop();
    digitalWrite(BUZ, LOW);
    digitalWrite(LEDPIN, LOW);
    buzzerOn = false;
  }
  server.send(200, "text/plain", geigerOn ? "ON" : "OFF");
}

// =====================================================================================
//  SETUP / LOOP  (Wi-Fi tuned for maximum power, range and stability)
// =====================================================================================
void wifiTune() {
  WiFi.setSleep(false);                           // radio never sleeps: lowest latency, stable link
  esp_wifi_set_ps(WIFI_PS_NONE);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);            // maximum transmit power of the ESP32 (19.5 dBm)
  esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20);   // 20 MHz channel: better sensitivity, range, stability
}

void setup() {
  setCpuFrequencyMhz(240);                        // full speed
  Serial.begin(115200);
  pinMode(BUZ, OUTPUT);
  pinMode(LEDPIN, OUTPUT);
  digitalWrite(BUZ, LOW);                         // off
  digitalWrite(LEDPIN, LOW);

  WiFi.persistent(false);                         // do not wear the flash
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("esp32-game");
  WiFi.setAutoReconnect(true);
  WiFi.setScanMethod(WIFI_ALL_CHANNEL_SCAN);                 // look at all channels...
  WiFi.setSortMethod(WIFI_CONNECT_AP_BY_SIGNAL);             // ...and join the strongest access point
  wifiTune();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  wifiTune();                                     // re-apply after connecting
  Serial.print("\nOpen: http://"); Serial.println(WiFi.localIP());
  if (MDNS.begin("esp32")) { MDNS.addService("http", "tcp", 80); Serial.println("or http://esp32.local"); }

  server.on("/", []() { server.send_P(200, "text/html", PAGE); });
  server.on("/data", []() { server.sendHeader("Cache-Control", "no-store"); server.send(200, "application/json", json()); });
  server.on("/on",  []() { buzzerOn = true;  digitalWrite(BUZ, HIGH); server.send(200, "text/plain", "ok"); });
  server.on("/off", []() { buzzerOn = false; digitalWrite(BUZ, LOW);  server.send(200, "text/plain", "ok"); });
  server.on("/speed", []() { server.send_P(200, "text/html", SPEED); });
  server.on("/ping", []() { server.sendHeader("Cache-Control", "no-store"); server.send(200, "text/plain", "ok"); });
  server.on("/dl", handleDownload);
  server.on("/up", HTTP_POST, []() { server.send(200, "text/plain", "ok"); });
  server.on("/game", []() { server.send_P(200, "text/html", GAME); });
  server.on("/geiger", handleGeiger);
  ws.begin();
  ws.onEvent(wsEvent);
  randomSeed(micros());
  resetGame();
  server.begin();
}

void loop() {
  server.handleClient();
  ws.loop();
  gameStream();
  geigerTick();

  unsigned long now = millis();
  if (now - lastSample >= 100) {
    lastSample = now;
    if (WiFi.status() == WL_CONNECTED) { int r = WiFi.RSSI(); addSample(r); rssiEma += 0.3f * (r - rssiEma); }
  }

  // Wi-Fi watchdog: if the link is down for 8 s, force a clean reconnect
  static unsigned long downSince = 0;
  if (WiFi.status() != WL_CONNECTED) {
    if (!downSince) downSince = now;
    if (now - downSince > 8000) { WiFi.disconnect(); WiFi.reconnect(); downSince = now; }
  } else {
    if (downSince) wifiTune();                    // link came back: re-apply radio settings
    downSince = 0;
  }

  if (!wsActive && !geigerOn) delay(1);           // be nice to the CPU when nothing is streaming
}
