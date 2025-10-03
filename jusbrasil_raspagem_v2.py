# -*- coding: utf-8 -*-

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import sys
import re # Importado para limpeza de nomes de arquivo
from datetime import datetime # Importado para criar o timestamp

# --- CONFIGURAÇÕES ---
URL_BUSCA = "https://www.jusbrasil.com.br/jurisprudencia/busca?q=opera%C3%A7%C3%A3o%20Lava%20Jato&dateFrom=2015-01-01&dateTo=2015-12-31"

# Lógica de pastas aprimorada para organizar os scrapes por sessão
PASTA_RAIZ = "decisoes_jusbrasil" # Pasta principal para todos os scrapes
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") # Cria uma string com a data e hora atuais
PASTA_SAIDA_SESSAO = os.path.join(PASTA_RAIZ, timestamp) # Cria o caminho para a subpasta da sessão atual

os.makedirs(PASTA_SAIDA_SESSAO, exist_ok=True)
print(f"✅ O script está rodando a partir de: {os.getcwd()}")
print(f"📂 Os arquivos desta sessão serão salvos em: {os.path.abspath(PASTA_SAIDA_SESSAO)}")


def limpar_nome_arquivo(titulo):
    """Remove caracteres inválidos de um título e o encurta para usá-lo como nome de arquivo."""
    # Remove caracteres inválidos em nomes de arquivo do Windows/Linux/Mac
    titulo_limpo = re.sub(r'[\\/*?:"<>|]', "", titulo)
    # Substitui múltiplos espaços ou quebras de linha por um único sublinhado
    titulo_limpo = re.sub(r'\s+', '_', titulo_limpo)
    # Limita o comprimento para evitar nomes de arquivo excessivamente longos
    titulo_limpo = titulo_limpo[:150]
    return titulo_limpo

# Opções do Chrome 
options = uc.ChromeOptions()
options.add_argument("--user-data-dir=C:/Temp/ChromeSelenium")
options.add_argument("--profile-directory=Default")
options.add_argument('--start-maximized')

# Inicializamos o driver usando 'uc.Chrome' e forçando a versão correta
print("Iniciando navegador com undetected-chromedriver...")
try:
    # Tente com a versão que funcionou. Se atualizar o Chrome, mude este número.
    driver = uc.Chrome(options=options, version_main=138)
except TypeError:
    # Fallback para caso a versão do undetected-chromedriver não aceite 'version_main'
    driver = uc.Chrome(options=options)


# --- EXECUÇÃO PRINCIPAL ---
driver.get(URL_BUSCA)

print("⏳ Aguardando verificação do Cloudflare e carregamento da página...")
print("   (O undetected-chromedriver tentará resolver isso automaticamente)")
input("✅ Quando a página de resultados estiver visível e COMPLETAMENTE CARREGADA, pressione ENTER no terminal...")

# --- COLETA DE LINKS ---
print("🔍 Coletando links da página de resultados...")

script = """
return Array.from(document.querySelectorAll('h2[class*="shared-styles_title"] a'))
            .map(el => el.href);
"""
urls = driver.execute_script(script)

if not urls:
    print("⚠️ Nenhum link foi encontrado. Verifique se os resultados da busca estão visíveis ou se o seletor CSS mudou.")
    driver.quit()
else:
    print(f"✅ {len(urls)} links coletados. Iniciando extração dos textos...")

    wait = WebDriverWait(driver, 20)

    # Lista de seletores robustos para tentar, em ordem de prioridade
    SELETORES_DE_TITULO = [
        ".document-title h1",              # Seletor para páginas de jurisprudência clássicas
        'div[class*="header_header"] h1'   # Seletor para outros layouts de página mais modernos
    ]

    for i, url in enumerate(urls, 1):
        print(f"\n📄 Processando {i}/{len(urls)}: {url}")
        try:
            driver.get(url)
            time.sleep(2) # Pausa para carregamento inicial da página

            # Lógica "Camaleão": Tenta encontrar o título usando a lista de seletores
            nome_arquivo = f"decisao_{i:03}.txt" # Nome padrão de fallback
            titulo_encontrado = False
            
            for seletor in SELETORES_DE_TITULO:
                try:
                    # Tenta encontrar o título com o seletor atual (espera no máximo 5 segundos)
                    titulo_elemento = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor)))
                    titulo_documento = titulo_elemento.text
                    
                    if titulo_documento: # Garante que o título não está vazio
                        nome_limpo = limpar_nome_arquivo(titulo_documento)
                        nome_arquivo = f"{nome_limpo}.txt"
                        print(f"   ✓ Título encontrado com o seletor: '{seletor}'")
                        print(f"   ✓ Nome do arquivo definido como: {nome_arquivo}")
                        titulo_encontrado = True
                        break # Se encontrou com sucesso, para de tentar outros seletores
                except Exception:
                    # Se o seletor não funcionou, apenas informa e continua para o próximo
                    print(f"   - Seletor '{seletor}' não encontrado. Tentando o próximo...")
            
            if not titulo_encontrado:
                 print(f"   ⚠️ Não foi possível extrair o título com nenhum seletor. Usando nome padrão.")

            # Clica no botão "Inteiro Teor"
            botao_inteiro_teor = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Inteiro Teor')]")))
            botao_inteiro_teor.click()
            time.sleep(1) # Pequena pausa após o clique para o conteúdo carregar

            # Extrai o texto completo
            texto_div = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='rich-text']")))
            texto = texto_div.text

            caminho_arquivo = os.path.join(PASTA_SAIDA_SESSAO, nome_arquivo)
            
            with open(caminho_arquivo, "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\n\n")
                f.write(texto)

            print(f"   ✅ Texto salvo em '{caminho_arquivo}'")

        except Exception as e:
            print(f"   ❌ Erro fatal ao processar o link {i}: {e}")
            screenshot_name = f"erro_fatal_{i:03}.png"
            screenshot_path = os.path.join(PASTA_SAIDA_SESSAO, screenshot_name)
            driver.save_screenshot(screenshot_path)
            print(f"   📸 Screenshot de erro salvo em '{screenshot_path}'")

# --- FINALIZAÇÃO ---
print("\n🎉 Processo de raspagem concluído!")
driver.quit()