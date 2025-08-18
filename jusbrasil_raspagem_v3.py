import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import os
import sys
import re
from datetime import datetime

# --- CONFIGURAÇÕES ---
URL_BASE_BUSCA = "https://www.jusbrasil.com.br/jurisprudencia/busca?q=opera%C3%A7%C3%A3o%20Lava%20Jato&dateFrom=2015-01-01&dateTo=2015-12-31"
NUMERO_MAXIMO_DE_PAGINAS = 10 

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
options.add_argument('--start-maximized')

print("Iniciando navegador com undetected-chromedriver...")
try:
    driver = uc.Chrome(options=options)
except TypeError:
    driver = uc.Chrome(options=options)

# --- EXECUÇÃO PRINCIPAL ---
driver.get("https://www.jusbrasil.com.br")
print("\n" + "---" * 25)
print("⚠️ AÇÃO NECESSÁRIA ⚠️")
print("Faça o login no site do Jusbrasil. Se aparecer algum pop-up, feche-o.")
input("Após o login, quando estiver pronto, pressione ENTER aqui no terminal para continuar...")
print("✅ Ok, continuando a execução...")


pagina_atual = 1
while True:
    if NUMERO_MAXIMO_DE_PAGINAS and pagina_atual > NUMERO_MAXIMO_DE_PAGINAS:
        print(f"\n✅ Limite de {NUMERO_MAXIMO_DE_PAGINAS} páginas atingido. Encerrando a raspagem.")
        break

    print(f"\n" + "---" * 25)
    print(f"--- 📄 Construindo e acessando a Página de Resultados {pagina_atual} ---")
    print("---" * 25)

    url_de_busca_paginada = f"{URL_BASE_BUSCA}&p={pagina_atual}"
    driver.get(url_de_busca_paginada)

    wait = WebDriverWait(driver, 20)
    try:
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[class*="container-results"]')))
        time.sleep(2)
        print("🔍 Página de resultados carregada. Coletando links...")
    except Exception as e:
        print(f"⚠️ Não foi possível carregar a página de resultados {pagina_atual}. Erro: {e}")
        break

    script_coleta = "return Array.from(document.querySelectorAll('h2[class*=\"shared-styles_title\"] a')).map(el => el.href);"
    urls_pagina = driver.execute_script(script_coleta)

    if not urls_pagina:
        print("❌ Nenhum link encontrado nesta página. Fim da raspagem.")
        break

    print(f"✅ {len(urls_pagina)} links coletados na página {pagina_atual}. Processando...")

    SELETORES_DE_TITULO = [".document-title h1", 'div[class*="header_header"] h1']
    
    # --- MODIFICAÇÃO: Adicionado mais um seletor à lista do Plano B ---
    SELETORES_PLANO_B = [
        "div[class*='DocumentPage-content']",      # Tentativa 1 para conteúdo sem abas
        "div[data-id='document-view-content']",   # Tentativa 2 para conteúdo sem abas
        "div[data-doc-artifact='JURISPRUDENCIA']"  # <-- NOVO: Adicionado seletor para o layout com 'data-doc-artifact'
    ]

    for i, url in enumerate(urls_pagina, 1):
        print(f"\n   -> Processando link {i}/{len(urls_pagina)} da página {pagina_atual}: {url}")
        try:
            driver.get(url)

            # Extração do Título
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

            # Extração da Ementa
            texto_ementa = ""
            try:
                seletor_ementa_xpath = "//h2[contains(text(), 'Ementa')]/following-sibling::p[1]"
                ementa_elemento = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, seletor_ementa_xpath)))
                texto_ementa = ementa_elemento.text
                print("      ✓ Ementa (Resumo) encontrada.")
            except TimeoutException:
                print("      ⓘ Não foi encontrada uma Ementa (Resumo) para este documento.")

            # Extração de Fatos
            texto_fatos = ""
            try:
                seletor_botao_fatos = "//a[contains(text(), 'Fatos')]"
                botao_fatos = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, seletor_botao_fatos)))
                botao_fatos.click()
                time.sleep(1)
                seletor_conteudo_fatos = "//div[@role='tabpanel' and @data-state='active']//p"
                conteudo_fatos_p = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, seletor_conteudo_fatos)))
                texto_fatos = conteudo_fatos_p.text
                print("      ✓ Conteúdo de 'Fatos' encontrado.")
            except TimeoutException:
                print("      ⓘ Aba 'Fatos' não encontrada. Continuando...")
            
            # Extração do Inteiro Teor (Lógica Plano A / Plano B)
            texto_inteiro_teor = ""
            inteiro_teor_encontrado = False
            
            # Plano A
            try:
                print("      → Plano A: Tentando encontrar a aba 'Inteiro Teor'...")
                seletor_inteiro_teor = "//*[(self::a or self::button) and contains(text(), 'Inteiro Teor')]"
                botao_inteiro_teor = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, seletor_inteiro_teor)))
                botao_inteiro_teor.click()
                time.sleep(1)
                texto_inteiro_teor_div = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='rich-text']")))
                texto_inteiro_teor = texto_inteiro_teor_div.text
                inteiro_teor_encontrado = True
                print("      ✓ Plano A bem-sucedido.")
            except TimeoutException:
                print("      ⚠️ Plano A falhou. Ativando Plano B...")

            # Plano B
            if not inteiro_teor_encontrado:
                for idx, seletor in enumerate(SELETORES_PLANO_B, 1):
                    try:
                        print(f"      → Plano B: Tentativa {idx}/{len(SELETORES_PLANO_B)} com o seletor '{seletor}'...")
                        conteudo_principal_div = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor)))
                        texto_inteiro_teor = conteudo_principal_div.text
                        if texto_inteiro_teor:
                            inteiro_teor_encontrado = True
                            print(f"      ✓ Plano B bem-sucedido.")
                            break
                    except TimeoutException:
                        continue
            
            # Salvamento condicional
            if inteiro_teor_encontrado and texto_inteiro_teor.strip():
                caminho_arquivo = os.path.join(PASTA_SAIDA_SESSAO, nome_arquivo)
                with open(caminho_arquivo, "w", encoding="utf-8") as f:
                    f.write(f"URL: {url}\n\n")
                    if texto_ementa:
                        f.write("Ementa:\n")
                        f.write(texto_ementa)
                        f.write("\n\n---\n\n")
                    if texto_fatos:
                        f.write("Fatos:\n")
                        f.write(texto_fatos)
                        f.write("\n\n---\n\n")
                    f.write("Inteiro Teor:\n")
                    f.write(texto_inteiro_teor)
                print(f"      ✅ Texto salvo em '{os.path.basename(caminho_arquivo)}'")
            else:
                print("      ❌ INTEIRO TEOR NÃO ENCONTRADO. Nenhum arquivo será salvo para este link.")

        except Exception as e:
            print(f"      ❌ Erro INESPERADO ao processar o link: {e}")
            screenshot_name = f"erro_inesperado_pag{pagina_atual}_{i:03}.png"
            screenshot_path = os.path.join(PASTA_SAIDA_SESSAO, screenshot_name)
            driver.save_screenshot(screenshot_path)
            print(f"      📸 Screenshot de erro salvo em '{screenshot_path}'.")

    pagina_atual += 1

print("\n🎉 Processo de raspagem concluído!")
driver.quit()
