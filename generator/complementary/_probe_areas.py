import urllib.request, re
UA={"User-Agent":"probe/1.0"}
def links(u):
    req=urllib.request.Request(u,headers=UA)
    h=urllib.request.urlopen(req,timeout=40).read().decode("utf-8","replace")
    return re.findall(r'href="([^"?][^"]*)"',h)
for u in [
 "https://ftp.ibge.gov.br/",
 "https://ftp.ibge.gov.br/organizacao_do_territorio",
 "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/",
]:
    try:
        L=[x for x in links(u) if not x.startswith('/') and x not in ('../',)]
        print("== OK",u); print(L[:60])
    except Exception as e:
        print("== ERR",u,e)
