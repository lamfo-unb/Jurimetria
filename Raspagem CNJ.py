# -*- coding: utf-8 -*-

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import os
import re
from datetime import datetime
import pandas as pd
import random

# --- CONFIGURAÇÕES GLOBAIS ---
URL_BASE_BUSCA = "https://comunica.pje.jus.br/consulta?texto=%22opera%C3%A7%C3%A3o%20lava%20jato%22&dataDisponibilizacaoInicio=2015-01-01&dataDisponibilizacaoFim=2025-10-03"

# --- MODOS DE PARADA CUSTOMIZADOS ---
NUMERO_MAXIMO_DE_PAGINAS = 50 
LIMITE_SUCESSOS_SESSAO = 400
LIMITE_ERROS_SESSAO = 15

# --- ESTRUTURA DE ARQUIVOS CENTRALIZADA ---
# !!! ATENÇÃO: Verifique se este caminho está correto para o seu computador !!!
PASTA_BASE_DE_DADOS = r"C:\Users\Felipe Loureiro\Desktop\Projeto Jurimetria PJE\base de dados"
PASTA_SAIDA_TEXTOS = os.path.join(PASTA_BASE_DE_DADOS, "decisoes_salvas_pje")

ARQUIVO_REGISTRO_CSV = os.path.join(PASTA_BASE_DE_DADOS, "registro_processamento_pje.csv")
ARQUIVO_REGISTRO_XLSX = os.path.join(PASTA_BASE_DE_DADOS, "registro_processamento_pje.xlsx")

os.makedirs(PASTA_SAIDA_TEXTOS, exist_ok=True)
print(f"✅ O script está rodando a partir de: {os.getcwd()}")
print(f"📂 A base de dados e os arquivos serão salvos em: {os.path.abspath(PASTA_BASE_DE_DADOS)}")

# --- FUNÇÕES AUXILIARES ---
def limpar_nome_arquivo(titulo):
    titulo_limpo = re.sub(r'[\\/*?:"<>|]', "", titulo)
    titulo_limpo = re.sub(r'\s+', '_', titulo_limpo)
    return titulo_limpo[:150]

def salvar_progresso(df_para_salvar):
    try:
        df_para_salvar.to_csv(ARQUIVO_REGISTRO_CSV, index=False, encoding='utf-8-sig')
        df_para_salvar.to_excel(ARQUIVO_REGISTRO_XLSX, index=False)
        print(f"💾 Progresso salvo com sucesso em CSV e XLSX.")
    except Exception as e:
        print(f"🚨 ERRO AO SALVAR O PROGRESSO: {e}")

# --- INICIALIZAÇÃO DA BASE DE DADOS ---
print("\n--- Carregando Base de Dados ---")
COLUNAS_REGISTRO = ['url', 'status', 'timestamp_processamento', 'nome_arquivo_salvo', 'detalhe_erro']
try:
    df_registro = pd.read_csv(ARQUIVO_REGISTRO_CSV)
    print(f"📖 Base de dados encontrada. {len(df_registro)} registros carregados.")
except FileNotFoundError:
    df_registro = pd.DataFrame(columns=COLUNAS_REGISTRO)
    print("📖 Nenhuma base de dados encontrada. Um novo arquivo será criado.")

urls_processadas = set(df_registro['url'])

# --- INICIALIZAÇÃO DO NAVEGADOR ---
options = uc.ChromeOptions()
options.add_argument('--start-maximized')
print("\nIniciando navegador com undetected-chromedriver...")

# NOTA: Se o erro de versão voltar, descomente a linha com "version_main"
# Exemplo: driver = uc.Chrome(version_main=140, options=options)
driver = uc.Chrome(options=options)

# --- EXECUÇÃO PRINCIPAL ---
sucessos_nesta_sessao = 0
erros_nesta_sessao = 0
parada_solicitada = False
pagina_atual = 1

# Carrega a página inicial ANTES de entrar no loop
print(f"Carregando página de busca inicial: {URL_BASE_BUSCA}")
driver.get(URL_BASE_BUSCA)

# --- PASSO DE DEPURAÇÃO ---
print("\n" + "---" * 25)
print("⚠️ AÇÃO NECESSÁRIA - OBSERVE O NAVEGADOR ⚠️")
input("O navegador abriu. Verifique se há pop-ups ou banners de cookies e feche-os. Após isso, pressione ENTER aqui no terminal para continuar...")
print("✅ Ok, continuando a execução...")

while True:
    if NUMERO_MAXIMO_DE_PAGINAS and pagina_atual > NUMERO_MAXIMO_DE_PAGINAS:
        print(f"\n🛑 Limite de {NUMERO_MAXIMO_DE_PAGINAS} páginas atingido. Encerrando.")
        break

    print(f"\n" + "---" * 25)
    print(f"--- 📄 Página {pagina_atual} | Sucessos: {sucessos_nesta_sessao} | Erros: {erros_nesta_sessao} ---")
    print("---" * 25)

    try:
        # Espera Robusta: Aguarda os links dos resultados se tornarem visíveis
        seletor_dos_links = "a.titulo-link"
        print(f"Aguardando os links ({seletor_dos_links}) da página aparecerem...")
        WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, seletor_dos_links))
        )
        time.sleep(2) 
        print("🔍 Links encontrados. Coletando URLs...")
    
    except TimeoutException:
        print(f"❌ ERRO CRÍTICO: O tempo de espera esgotou e nenhum link foi encontrado na página {pagina_atual}.")
        screenshot_name = f"erro_fatal_pagina_{pagina_atual}.png"
        screenshot_path = os.path.join(PASTA_BASE_DE_DADOS, screenshot_name)
        driver.save_screenshot(screenshot_path)
        print(f"📸 Screenshot do erro salvo em '{screenshot_path}'. Verifique a imagem.")
        break
    
    script_coleta = f"return Array.from(document.querySelectorAll('{seletor_dos_links}')).map(el => el.href);"
    urls_pagina = driver.execute_script(script_coleta)
    
    print(f"✅ Coleta concluída. {len(urls_pagina)} links foram encontrados nesta página.")

    if not urls_pagina:
        print("❌ Nenhum link retornado pelo script. Fim dos resultados.")
        break
    
    novos_registros = []

    for i, url in enumerate(urls_pagina, 1):
        print(f"\n   -> Processando link {i}/{len(urls_pagina)} da pág {pagina_atual}: {url[:70]}...")

        if url in urls_processadas:
            print("   -> 🟡 URL já consta na base de dados. Pulando.")
            continue
        
        log_entry = {col: None for col in COLUNAS_REGISTRO}
        log_entry['url'] = url
        log_entry['timestamp_processamento'] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        try:
            driver.get(url)
            
            titulo_documento = ""
            try:
                titulo_elemento = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.titulo-documento"))
                )
                titulo_documento = titulo_elemento.text
                nome_limpo = limpar_nome_arquivo(titulo_documento)
                nome_arquivo = f"{nome_limpo}.txt"
                print(f"      ✓ Título encontrado: {nome_arquivo[:50]}...")
            except TimeoutException:
                print("      ⚠️ Não foi possível extrair o título. Usando nome padrão.")
                nome_arquivo = f"decisao_pag{pagina_atual}_{i:03}.txt"
            
            texto_completo = ""
            try:
                # Extração Robusta: Usando o XPath relativo que discutimos
                xpath_conteudo = "//div[@class='conteudo-ato']"
                conteudo_div = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, xpath_conteudo))
                )
                texto_completo = conteudo_div.text
                print("      ✓ Conteúdo do documento encontrado com XPath robusto.")
            except TimeoutException:
                print(f"      ❌ ERRO: Conteúdo não encontrado com o XPath: {xpath_conteudo}")
                log_entry['status'] = 'erro_conteudo_nao_encontrado'
                log_entry['detalhe_erro'] = f'Seletor XPath "{xpath_conteudo}" não encontrado.'
                novos_registros.append(log_entry)
                continue

            caminho_arquivo = os.path.join(PASTA_SAIDA_TEXTOS, nome_arquivo)
            with open(caminho_arquivo, "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\n\n")
                f.write(f"TÍTULO: {titulo_documento}\n\n")
                f.write(f"--- CONTEÚDO ---\n{texto_completo}")
            
            print(f"      ✅ Texto completo salvo em '{os.path.basename(caminho_arquivo)}'")
            log_entry['status'] = 'sucesso'
            log_entry['nome_arquivo_salvo'] = nome_arquivo

        except Exception as e:
            print(f"      ❌ Erro INESPERADO ao processar o link: {e}")
            screenshot_name = f"erro_{limpar_nome_arquivo(url)}.png"
            screenshot_path = os.path.join(PASTA_BASE_DE_DADOS, screenshot_name)
            driver.save_screenshot(screenshot_path)
            print(f"      📸 Screenshot de erro salvo em '{screenshot_path}'.")
            
            log_entry['status'] = 'erro_inesperado'
            log_entry['detalhe_erro'] = str(e).replace('\n', ' ')

        novos_registros.append(log_entry)

        if log_entry['status'] == 'sucesso': sucessos_nesta_sessao += 1
        elif log_entry['status'].startswith('erro_'): erros_nesta_sessao += 1

        if (LIMITE_SUCESSOS_SESSAO and sucessos_nesta_sessao >= LIMITE_SUCESSOS_SESSAO) or \
           (LIMITE_ERROS_SESSAO and erros_nesta_sessao >= LIMITE_ERROS_SESSAO):
            print(f"\n🛑 LIMITE DE SUCESSOS/ERROS ATINGIDO. Encerrando a raspagem.")
            parada_solicitada = True
            break
            
    if novos_registros:
        print(f"\n--- Fim da página {pagina_atual}. Salvando {len(novos_registros)} novos registros... ---")
        novos_df = pd.DataFrame(novos_registros)
        df_registro = pd.concat([df_registro, novos_df], ignore_index=True)
        salvar_progresso(df_registro)
        urls_processadas.update(novos_df['url'])
        novos_registros = []
    
    if parada_solicitada: break

    try:
        print("\n--- Navegando para a próxima página ---")
        seletor_proxima_pagina = "//button[@aria-label='Próxima página' and not(@disabled)]"
        botao_proxima = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, seletor_proxima_pagina))
        )
        driver.execute_script("arguments[0].click();", botao_proxima)
        print("✅ Clique no botão 'Próxima página' realizado.")
        
        pagina_atual += 1
        delay = random.uniform(4, 8)
        print(f"--- Pausa de {delay:.2f} segundos para a nova página carregar ---")
        time.sleep(delay)

    except (TimeoutException, NoSuchElementException):
        print("\n🏁 Botão 'Próxima página' não encontrado ou desabilitado. Fim da raspagem.")
        break

# --- FIM DA EXECUÇÃO ---
print("\n🎉 Processo de raspagem concluído!")
driver.quit()