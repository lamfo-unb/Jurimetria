import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import time
import os
import re
from datetime import datetime
import pandas as pd
import random
from urllib.parse import unquote

# --- CONFIGURAÇÕES GLOBAIS ---
LISTA_URLS_BASE = [
    "https://www.jusbrasil.com.br/jurisprudencia/busca?dateFrom=2015-01-01&dateTo=2015-09-24&q=%22opera%C3%A7%C3%A3o+Lava+Jato%22",
    "https://www.jusbrasil.com.br/jurisprudencia/busca?dateFrom=2015-09-24&dateTo=2016-04-29&q=%22opera%C3%A7%C3%A3o+Lava+Jato%22",
    "https://www.jusbrasil.com.br/jurisprudencia/busca?dateFrom=2016-04-29&dateTo=2016-09-14&q=%22opera%C3%A7%C3%A3o+Lava+Jato%22",
    "https://www.jusbrasil.com.br/jurisprudencia/busca?dateFrom=2016-09-14&dateTo=2017-02-16&q=%22opera%C3%A7%C3%A3o+Lava+Jato%22",
    "https://www.jusbrasil.com.br/jurisprudencia/busca?dateFrom=2017-02-16&dateTo=2017-06-06&q=%22opera%C3%A7%C3%A3o+Lava+Jato%22",
    "https://www.jusbrasil.com.br/jurisprudencia/busca?dateFrom=2017-06-06&dateTo=2017-09-20&q=%22opera%C3%A7%C3%A3o+Lava+Jato%22",
    "https://www.jusbrasil.com.br/jurisprudencia/busca?dateFrom=2017-09-20&dateTo=2017-12-19&q=%22opera%C3%A7%C3%A3o+Lava+Jato%22"
]
PAGINA_INICIAL = 1
NUMERO_MAXIMO_DE_PAGINAS = 500

# --- ESTRUTURA DE ARQUIVOS ---
PASTA_RAIZ_DADOS = "descobertas_jusbrasil"
os.makedirs(PASTA_RAIZ_DADOS, exist_ok=True)

ARQUIVO_REGISTRO_CSV = os.path.join(PASTA_RAIZ_DADOS, "registro_descoberta.csv")
ARQUIVO_REGISTRO_XLSX = os.path.join(PASTA_RAIZ_DADOS, "registro_descoberta.xlsx")

print(f"✅ O script está rodando a partir de: {os.getcwd()}")
print(f"📂 O banco de dados de descoberta será salvo em: {os.path.abspath(PASTA_RAIZ_DADOS)}")

# --- FUNÇÕES AUXILIARES ---
def extrair_tribunal_e_processo(texto_titulo):
    tribunal, numero_processo = "N/A", "N/A"
    match_tribunal = re.search(r'^([A-Z]{2,}(?:-[A-Z]{2})?-\d{1,2}|[A-Z]{3,})', texto_titulo)
    if match_tribunal: tribunal = match_tribunal.group(1)
    
    padroes_processo = [
        r'(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})', r'(\d{5,}-\d{2}\.\d{4}\.\d{2,}\.\d{4})',
        r'[\s:]([A-Z]{2,}\s\d{2,})', r'(\d{10,})'
    ]
    for padrao in padroes_processo:
        match_processo = re.search(padrao, texto_titulo)
        if match_processo:
            numero_processo = match_processo.group(1).strip()
            break
    return tribunal, numero_processo

def salvar_progresso(df_para_salvar, colunas):
    try:
        df_para_salvar = df_para_salvar[colunas]
        df_para_salvar.to_csv(ARQUIVO_REGISTRO_CSV, index=False, encoding='utf-8-sig')
        df_para_salvar.to_excel(ARQUIVO_REGISTRO_XLSX, index=False)
        print(f"💾 Progresso salvo com sucesso em CSV e XLSX.")
    except Exception as e:
        print(f"🚨 ERRO AO SALVAR O PROGRESSO: {e}")

def human_scroll(driver):
    print("      -> Simulando rolagem humana...")
    total_height = driver.execute_script("return document.body.scrollHeight")
    for i in range(1, total_height, random.randint(300, 500)):
        driver.execute_script(f"window.scrollTo(0, {i});")
        time.sleep(random.uniform(0.2, 0.5))
    time.sleep(random.uniform(1, 2))
    driver.execute_script(f"window.scrollTo(0, {random.randint(400, 800)});")
    time.sleep(random.uniform(0.8, 1.5))

# --- INICIALIZAÇÃO DA BASE DE DADOS (UMA ÚNICA VEZ) ---
print("\n--- Carregando Banco de Dados de Descoberta ---")
COLUNAS_REGISTRO = ['Tribunal', 'Titulo Completo', 'Numero do Processo', 'Resumo (Ementa)', 'Link Jusbrasil', 'Status', 'Timestamp da Descoberta']
try:
    df_registro = pd.read_csv(ARQUIVO_REGISTRO_CSV)
    print(f"📖 Base de dados encontrada. {len(df_registro)} registros carregados.")
except FileNotFoundError:
    df_registro = pd.DataFrame(columns=COLUNAS_REGISTRO)
    print("📖 Nenhuma base de dados encontrada. Um novo arquivo será criado.")

for col in COLUNAS_REGISTRO:
    if col not in df_registro.columns: df_registro[col] = None

urls_ja_descobertas = set(df_registro['Link Jusbrasil'].dropna())
print(f"🧠 {len(urls_ja_descobertas)} links já estão na base e serão ignorados em todas as buscas.")

# --- LOOP PRINCIPAL: Itera sobre cada URL base da lista ---
for idx, url_base in enumerate(LISTA_URLS_BASE, 1):
    print("\n" + "="*80)
    
    try:
        termo_busca_raw = re.search(r'[?&]q=([^&]+)', url_base).group(1)
        termo_busca = unquote(termo_busca_raw.replace('+', ' '))
    except (AttributeError, IndexError):
        termo_busca = f"Busca Desconhecida {idx}"
        
    print(f"🚀 INICIANDO BUSCA {idx}/{len(LISTA_URLS_BASE)}: {termo_busca}")
    print("="*80)
    
    driver = None
    try:
        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        print("\nIniciando nova sessão do navegador...")
        driver = uc.Chrome(options=options)
        
        # <<< REMOVIDO: Bloco de login manual foi retirado para automação completa >>>
        
        pagina_atual = PAGINA_INICIAL
        novos_processos_nesta_busca = 0

        while True:
            if (pagina_atual - PAGINA_INICIAL + 1) > NUMERO_MAXIMO_DE_PAGINAS:
                print(f"\n🛑 Limite de {NUMERO_MAXIMO_DE_PAGINAS} páginas atingido para esta busca.")
                break

            print(f"\n--- 📄 Página {pagina_atual} | Novos nesta busca: {novos_processos_nesta_busca} ---")
            
            url_de_busca_paginada = f"{url_base}&p={pagina_atual}"
            
            try:
                driver.get(url_de_busca_paginada)
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='container-results']")))
                time.sleep(2)
                print("   -> Página de resultados carregada.")
            except Exception as e:
                print(f"   -> ⚠️ Não foi possível carregar os resultados da página {pagina_atual}. Erro: {e}")
                break

            resultados = driver.find_elements(By.CSS_SELECTOR, "li[class*='search-snippet-list_listItem']")
            if not resultados:
                print("   -> ✅ Fim dos resultados para esta busca.")
                break
            
            novos_registros_pagina = []

            for resultado in resultados:
                try:
                    link_element = resultado.find_element(By.CSS_SELECTOR, "h2 a")
                    url = link_element.get_attribute('href')
                    
                    if url in urls_ja_descobertas:
                        continue

                    titulo_completo = link_element.text
                    tribunal, numero_processo = extrair_tribunal_e_processo(titulo_completo)
                    
                    ementa = ""
                    try:
                        ementa_element = resultado.find_element(By.CSS_SELECTOR, "blockquote p")
                        ementa = ementa_element.text.replace("Ementa:", "").strip()
                    except NoSuchElementException:
                        pass

                    processo_info = {
                        'Tribunal': tribunal, 'Titulo Completo': titulo_completo, 'Numero do Processo': numero_processo,
                        'Resumo (Ementa)': ementa, 'Link Jusbrasil': url, 'Status': 'pendente_coleta',
                        'Timestamp da Descoberta': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    novos_registros_pagina.append(processo_info)
                    urls_ja_descobertas.add(url)
                    novos_processos_nesta_busca += 1

                except Exception as e:
                    print(f"      -> ❌ Erro ao extrair dados de um resultado: {e}")

            if novos_registros_pagina:
                print(f"   -> Adicionando {len(novos_registros_pagina)} novos processos ao registro...")
                novos_df = pd.DataFrame(novos_registros_pagina)
                df_registro = pd.concat([df_registro, novos_df], ignore_index=True)
                salvar_progresso(df_registro, COLUNAS_REGISTRO)
            else:
                print(f"   -> Nenhum processo novo para adicionar nesta página.")
            
            human_scroll(driver)
            delay = random.uniform(5, 10)
            print(f"   -> Pausa de {delay:.2f} segundos...")
            time.sleep(delay)

            pagina_atual += 1

    except Exception as e:
        print("\n" + "!"*80)
        print(f"🚨 ERRO GERAL AO PROCESSAR A URL BASE: {url_base} 🚨")
        print(f"ERRO: {e}")
        print("Passando para a próxima URL da lista...")
        print("!"*80)

    finally:
        if driver:
            print("\nEncerrando sessão do navegador...")
            driver.quit()

print("\n\n" + "*"*80)
print("🎉🎉🎉 PROCESSO DE DESCOBERTA CONCLUÍDO PARA TODAS AS URLS DA LISTA! 🎉🎉🎉")
print("*"*80)