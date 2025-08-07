# -*- coding: utf-8 -*-

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import sys
import re
from datetime import datetime

# --- CONFIGURAÇÕES ---
URL_BASE_BUSCA = "https://www.jusbrasil.com.br/jurisprudencia/busca?q=opera%C3%A7%C3%A3o%20Lava%20Jato&dateFrom=2015-01-01&dateTo=2015-12-31"

PASTA_RAIZ = "decisoes_jusbrasil"
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
PASTA_SAIDA_SESSAO = os.path.join(PASTA_RAIZ, timestamp)

os.makedirs(PASTA_SAIDA_SESSAO, exist_ok=True)
print(f"✅ O script está rodando a partir de: {os.getcwd()}")
print(f"📂 Os arquivos desta sessão serão salvos em: {os.path.abspath(PASTA_SAIDA_SESSAO)}")


def limpar_nome_arquivo(titulo):
    titulo_limpo = re.sub(r'[\\/*?:"<>|]', "", titulo)
    titulo_limpo = re.sub(r'\s+', '_', titulo_limpo)
    titulo_limpo = titulo_limpo[:150]
    return titulo_limpo

options = uc.ChromeOptions()
options.add_argument("--user-data-dir=C:/Temp/ChromeSelenium")
options.add_argument("--profile-directory=Default")
options.add_argument('--start-maximized')

print("Iniciando navegador com undetected-chromedriver...")
try:
    driver = uc.Chrome(options=options, version_main=138)
except TypeError:
    driver = uc.Chrome(options=options)

# --- EXECUÇÃO PRINCIPAL ---
# input("Faça login no Jusbrasil se necessário e, quando estiver pronto, pressione ENTER...")

pagina_atual = 1
while True:
    print(f"\n" + "---" * 25)
    print(f"--- 📄 Construindo e acessando a Página de Resultados {pagina_atual} ---")
    print("---" * 25)
    
    # Constrói a URL para a página de resultados atual
    url_de_busca_paginada = f"{URL_BASE_BUSCA}&p={pagina_atual}"
    driver.get(url_de_busca_paginada)
    
    wait = WebDriverWait(driver, 20)
    try:
        # Espera até que o container dos resultados esteja visível
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[class*="container-results"]')))
        time.sleep(2) 
        print("🔍 Página de resultados carregada. Coletando links...")
    except Exception as e:
        print(f"⚠️ Não foi possível carregar a página de resultados {pagina_atual}. Possivelmente o fim da busca. Erro: {e}")
        break

    script_coleta = "return Array.from(document.querySelectorAll('h2[class*=\"shared-styles_title\"] a')).map(el => el.href);"
    urls_pagina = driver.execute_script(script_coleta)

    # CONDIÇÃO DE PARADA: Se não encontrar mais links, encerra o script.
    if not urls_pagina:
        print("✅ Nenhum link encontrado nesta página. Fim da raspagem.")
        break
    
    print(f"✅ {len(urls_pagina)} links coletados na página {pagina_atual}. Processando...")
    
    SELETORES_DE_TITULO = [".document-title h1", 'div[class*="header_header"] h1']

    # Loop para processar os links coletados. Não usa mais driver.back()
    for i, url in enumerate(urls_pagina, 1):
        print(f"\n   -> Processando link {i}/{len(urls_pagina)} da página {pagina_atual}: {url}")
        try:
            driver.get(url)

            nome_arquivo = f"decisao_pag{pagina_atual}_{i:03}.txt"
            titulo_encontrado = False
            for seletor in SELETORES_DE_TITULO:
                try:
                    titulo_elemento = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor)))
                    titulo_documento = titulo_elemento.text
                    if titulo_documento:
                        nome_limpo = limpar_nome_arquivo(titulo_documento)
                        nome_arquivo = f"{nome_limpo}.txt"
                        print(f"      ✓ Título encontrado: {nome_arquivo[:50]}...")
                        titulo_encontrado = True
                        break
                except Exception:
                    continue
            
            if not titulo_encontrado:
                 print(f"      ⚠️ Não foi possível extrair o título. Usando nome padrão.")

            botao_inteiro_teor = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Inteiro Teor')]")))
            botao_inteiro_teor.click()
            time.sleep(1)

            texto_div = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='rich-text']")))
            texto = texto_div.text

            caminho_arquivo = os.path.join(PASTA_SAIDA_SESSAO, nome_arquivo)
            with open(caminho_arquivo, "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\n\n")
                f.write(texto)
            print(f"      ✅ Texto salvo em '{os.path.basename(caminho_arquivo)}'")

        except Exception as e:
            print(f"      ❌ Erro fatal ao processar o link individual: {e}")
            screenshot_name = f"erro_link_pag{pagina_atual}_{i:03}.png"
            screenshot_path = os.path.join(PASTA_SAIDA_SESSAO, screenshot_name)
            driver.save_screenshot(screenshot_path)
            print(f"      📸 Screenshot de erro salvo.")
    
    # Avança para a próxima página para a próxima iteração do loop 'while'
    pagina_atual += 1

# --- FINALIZAÇÃO ---
print("\n🎉 Processo de raspagem concluído!")
driver.quit()