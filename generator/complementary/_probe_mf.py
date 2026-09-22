import urllib.request, json, re
UA={"User-Agent":"AgrocoreEstudos/1.0"}
def get(u, t=40):
    return urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t).read()
tries=[
 ("dadosgov_ckan","https://dados.gov.br/api/3/action/package_search?q=m%C3%B3dulo+fiscal&rows=10"),
 ("incra_ckan","https://dadosabertos.incra.gov.br/api/3/action/package_search?q=modulo+fiscal&rows=10"),
]
for nome,u in tries:
    try:
        d=json.loads(get(u).decode("utf-8","replace"))
        res=d.get("result",{}); n=res.get("count"); pkgs=res.get("results",[])
        print(f"== {nome}: count={n}")
        for p in pkgs[:6]:
            title=p.get("title") or p.get("name")
            recs=[(r.get("format"),r.get("url")) for r in p.get("resources",[]) if r.get("format","").lower() in ("csv","xlsx","xls","ods")]
            print("  -",title[:70])
            for f,url in recs[:4]:
                print("     ",f,url)
    except Exception as e:
        print(f"== {nome}: ERRO {type(e).__name__} {e}")
