"""Simulator & operator view inside the academy page.

The simulator (:8190) and NAVERA's operator view (:8181) are plain-http servers started by the
teacher (the full simulator is teacher-only; students fly Sim Lite), from a sandbox copy of NAVERA. Through the internet the academy
is https and a browser refuses an http page inside it, so the academy carries them under its own
address (/web/sim/…, /web/op/…), behind the academy login: only the teacher can see or drive them here
(run_sim.sh itself listens on the local network too). Their pages use absolute paths (/api/…, /tiles/…): a small script added to
each page sends those under the same prefix. NAVERA's own files are not changed.
"""
import json
import re
import urllib.error
import urllib.request

PORTS = {"sim": 8190, "op": 8181}
NAMES = {"sim": "mission simulator", "op": "operator view"}
_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization",
        "proxy-authenticate", "content-length", "content-encoding", "host", "cookie", "content-type"}

_PATCH = """<script>(function(){var P=%s;
var L=location.origin;function f(u){if(typeof u!=='string')return u;if(u.indexOf(L+'/')===0)u=u.slice(L.length);
return (u[0]==='/'&&u[1]!=='/'&&u.indexOf('/web/')!==0)?P+u:u}
var F=window.fetch;window.fetch=function(u,o){return F.call(this,typeof u==='string'?f(u):u,o)};
var O=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(m,u){arguments[1]=f(u);return O.apply(this,arguments)};
if(window.EventSource){var E=window.EventSource;window.EventSource=function(u,c){return new E(f(u),c)}}
[HTMLImageElement,HTMLScriptElement,HTMLIFrameElement,HTMLSourceElement,HTMLLinkElement,HTMLAnchorElement].forEach(function(C){
 ['src','href'].forEach(function(k){var d=Object.getOwnPropertyDescriptor(C.prototype,k);
 if(d&&d.set)Object.defineProperty(C.prototype,k,{get:d.get,set:function(v){d.set.call(this,f(v))},configurable:true})})});
var S=Element.prototype.setAttribute;Element.prototype.setAttribute=function(n,v){if(n==='src'||n==='href')v=f(v);return S.call(this,n,v)};
})();</script>"""

_ATTR = re.compile(r"""((?:src|href|action)\s*=\s*["'])/(?!/)""")


START_HELP = ("Take <b>Full mission simulator</b> in the Hardware menu, open a new terminal and run "
              "<code>cd ~/navera &amp;&amp; navera_tools/run_sim.sh</code>, then press <b>Try again</b>.")


def message(title, text, status, lite=False, retry=False):
    btn = ("display:inline-block;margin:6px;padding:9px 18px;border-radius:999px;text-decoration:none;font-weight:600;"
           "border:1px solid rgba(255,255,255,.4);color:#fff")
    links = ""
    if retry:
        links += f"<a style='{btn}' href='javascript:location.reload()'>⟳ Try again</a>"
    if lite or retry:
        links += (f"<a style='{btn};background:linear-gradient(135deg,#ff9f8a,#e8706a);color:#2a0d08;border:none' "
                  "href='javascript:history.length>1?history.back():location.replace(\"/static/simlite/index.html\")'>"
                  "🛩️ Back to Sim Lite</a>")
    page = ("<body style='margin:0;display:grid;place-items:center;height:100vh;font-family:Inter,system-ui,"
            "sans-serif;background:#0b1730;color:#f4f7fa;text-align:center'><div style='max-width:480px;"
            "padding:24px'><h2 style='font-family:Fraunces,Georgia,serif;font-weight:600'>%s</h2>"
            "<p style='opacity:.85;line-height:1.55'>%s</p><p>%s</p></div></body>") % (title, text, links)
    return page, status


def proxy(app, tool, sub, request):
    """Forward one request to the tool and return a Flask response."""
    qs = request.query_string.decode()
    url = f"http://127.0.0.1:{PORTS[tool]}/{sub}" + (f"?{qs}" if qs else "")
    hdrs = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    if request.content_type:
        hdrs["Content-Type"] = request.content_type
    req = urllib.request.Request(url, data=request.get_data() if request.method == "POST" else None,
                                 headers=hdrs, method=request.method)
    try:
        r = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        r = e
    except (urllib.error.URLError, OSError):
        return message(f"The {NAMES[tool]} is not running", START_HELP, 503, retry=True)
    ctype = r.headers.get("Content-Type", "application/octet-stream")
    out = [(k, v) for k, v in r.headers.items() if k.lower() not in _HOP]
    prefix = f"/web/{tool}"
    if ctype.startswith("text/html"):
        body = r.read().decode("utf-8", "replace")
        r.close()
        # links between the two tools, then plain absolute src/href in the page itself
        body = body.replace("`http://${location.hostname}:8181/operator`", "'/web/op/operator'")
        body = body.replace("`http://${location.hostname}:8190/`", "'/web/sim/'")
        body = _ATTR.sub(lambda m: m.group(1) + prefix + "/", body)
        patch = _PATCH % json.dumps(prefix)
        m = re.search(r"<head[^>]*>", body)
        body = body[:m.end()] + patch + body[m.end():] if m else patch + body
        return app.response_class(body, status=r.status, headers=out, content_type=ctype)

    def stream():
        try:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            r.close()
    return app.response_class(stream(), status=r.status, headers=out, content_type=ctype, direct_passthrough=True)
