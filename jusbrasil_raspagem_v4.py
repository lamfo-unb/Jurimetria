import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import os
import re
from datetime import datetime
import pandas as pd
import random

# --- CONFIGURAÇÕES GLOBAIS ---
URL_BASE_BUSCA = "https://www.jusbrasil.com.br/jurisprudencia/busca?q=opera%C3%A7%C3%A3o+Lava+Jato&dateFrom=2015-06-26&dateTo=2015-11-01"
PAGINA_INICIAL = 1

# --- MODOS DE PARADA CUSTOMIZADOS ---
NUMERO_MAXIMO_DE_PAGINAS = 50 
LIMITE_SUCESSOS_SESSAO = 400
LIMITE_ERROS_SESSAO = 15

# --- ESTRUTURA DE ARQUIVOS CENTRALIZADA ---
PASTA_BASE_DE_DADOS = r"C:\Users\Felipe Loureiro\Desktop\Projeto Jurimetria\base de dados nova"
PASTA_SAIDA_TEXTOS = os.path.join(PASTA_BASE_DE_DADOS, "decisoes_salvas")

ARQUIVO_REGISTRO_CSV = os.path.join(PASTA_BASE_DE_DADOS, "registro_processamento.csv")
ARQUIVO_REGISTRO_XLSX = os.path.join(PASTA_BASE_DE_DADOS, "registro_processamento.xlsx")

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

# --- INICIALIZAÇÃO DA BASE DE DADOS (PANDAS) ---
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
try:
    driver = uc.Chrome(options=options)
except TypeError:
    driver = uc.Chrome(options=options)

# --- INTERAÇÃO COM O USUÁRIO ---
driver.get("https://www.jusbrasil.com.br")
print("\n" + "---" * 25)
print("⚠️ AÇÃO NECESSÁRIA ⚠️")
print("Faça o login no site do Jusbrasil. Se aparecer algum pop-up, feche-o.")
input("Após o login, quando estiver pronto, pressione ENTER aqui no terminal para continuar...")
print("✅ Ok, continuando a execução...")

# --- EXECUÇÃO PRINCIPAL ---
sucessos_nesta_sessao = 0
erros_nesta_sessao = 0
parada_solicitada = False
pagina_atual = PAGINA_INICIAL

while True:
    if NUMERO_MAXIMO_DE_PAGINAS and (pagina_atual - PAGINA_INICIAL + 1) > NUMERO_MAXIMO_DE_PAGINAS:
        print(f"\n🛑 Limite de {NUMERO_MAXIMO_DE_PAGINAS} páginas a serem processadas foi atingido. Encerrando a raspagem.")
        break

    print(f"\n" + "---" * 25)
    print(f"--- 📄 Página {pagina_atual} | Sucessos: {sucessos_nesta_sessao} | Erros: {erros_nesta_sessao} ---")
    print("---" * 25)

    url_de_busca_paginada = f"{URL_BASE_BUSCA}&p={pagina_atual}"
    
    pagina_carregada_com_sucesso = False
    for tentativa in range(2):
        try:
            print(f"Carregando página de resultados (tentativa {tentativa + 1}/2)...")
            driver.get(url_de_busca_paginada)
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[class*="container-results"]')))
            time.sleep(2)
            print("🔍 Página de resultados carregada. Coletando links...")
            pagina_carregada_com_sucesso = True
            break
        except Exception as e:
            print(f"⚠️ Falha na tentativa {tentativa + 1}.")
            if tentativa == 0:
                screenshot_name = f"erro_pagina_{pagina_atual}.png"
                screenshot_path = os.path.join(PASTA_BASE_DE_DADOS, screenshot_name)
                driver.save_screenshot(screenshot_path)
                print(f"📸 Screenshot do erro salvo em '{screenshot_path}'. Verifique a imagem.")
                print("Aguardando 10 segundos antes de tentar novamente...")
                time.sleep(10)
            else:
                print(f"❌ Não foi possível carregar a página de resultados {pagina_atual} após 2 tentativas. Encerrando o script.")
    
    if not pagina_carregada_com_sucesso:
        break

    script_coleta = "return Array.from(document.querySelectorAll('h2[class*=\"shared-styles_title\"] a')).map(el => el.href);"
    urls_pagina = driver.execute_script(script_coleta)

    if not urls_pagina:
        print("❌ Nenhum link encontrado nesta página. Fim da raspagem.")
        break

    print(f"✅ {len(urls_pagina)} links coletados. Iniciando processamento...")
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
            
            nome_arquivo = f"decisao_pag{pagina_atual}_{i:03}.txt"
            titulo_documento = ""
            SELETORES_DE_TITULO = [".document-title h1", 'div[class*="header_header"] h1']
            for seletor in SELETORES_DE_TITULO:
                try:
                    titulo_elemento = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor)))
                    titulo_documento = titulo_elemento.text
                    if titulo_documento:
                        nome_limpo = limpar_nome_arquivo(titulo_documento)
                        nome_arquivo = f"{nome_limpo}.txt"
                        print(f"      ✓ Título encontrado: {nome_arquivo[:50]}...")
                        break
                except Exception:
                    continue
            
            if not titulo_documento:
                print(f"      ⚠️ Não foi possível extrair o título. Usando nome padrão.")
            
            texto_ementa = ""
            try:
                seletor_ementa_xpath = "//h2[contains(., 'Ementa') or contains(., 'Resumo')]/following-sibling::*[1]"
                ementa_elemento = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, seletor_ementa_xpath)))
                texto_ementa = ementa_elemento.text
                print("      ✓ Ementa (Resumo) encontrada.")
            except TimeoutException:
                print("      ⓘ Não foi encontrada uma Ementa (Resumo) para este documento.")

            texto_fatos = ""
            try:
                seletor_botao_fatos = "//a[contains(text(), 'Fatos')]"
                botao_fatos = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, seletor_botao_fatos)))
                driver.execute_script("arguments[0].click();", botao_fatos)
                time.sleep(1)
                seletor_conteudo_fatos = "//div[@role='tabpanel' and @data-state='active']//p"
                conteudo_fatos_p = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, seletor_conteudo_fatos)))
                texto_fatos = conteudo_fatos_p.text
                print("      ✓ Conteúdo de 'Fatos' encontrado.")
            except TimeoutException:
                print("      ⓘ Aba 'Fatos' não encontrada.")
                
            texto_inteiro_teor = ""
            inteiro_teor_encontrado = False
            
            # --- LÓGICA DE EXTRAÇÃO UNIFICADA E FINAL ---
            
            # Etapa 1: Tenta clicar na aba "Inteiro Teor". Se não conseguir, assume-se que a página já exibe o texto.
            try:
                seletor_inteiro_teor_btn = "//*[(self::a or self::button) and contains(text(), 'Inteiro Teor')]"
                botao_inteiro_teor = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, seletor_inteiro_teor_btn)))
                driver.execute_script("arguments[0].click();", botao_inteiro_teor)
                print("      ✓ Aba 'Inteiro Teor' clicada. Aguardando conteúdo...")
                time.sleep(1.5) # Pausa crucial para o conteúdo dinâmico carregar.
            except TimeoutException:
                print("      ⓘ Nenhuma aba 'Inteiro Teor' encontrada/clicável. Buscando texto direto na página.")
            
            # Etapa 2: Com o conteúdo visível (seja por clique ou por padrão), busca o texto em si.
            SELETORES_ROBUSTOS = [
                (By.XPATH, '//div[@data-doc-artifact="INTEIRO_TEOR"]', "Atributo 'INTEIRO_TEOR'"),
                (By.CSS_SELECTOR, "div[class*='rich-text']", "Classe 'rich-text' (pós-clique)"),
                (By.XPATH, '//div[@data-doc-artifact="JURISPRUDENCIA"]', "Atributo 'JURISPRUDENCIA'"),
                (By.XPATH, "//h2[contains(., 'Inteiro Teor')]/following-sibling::div[1]", "Título 'Inteiro Teor'"),
                (By.CSS_SELECTOR, "div[class*='DocumentPage-content']", "Classe 'DocumentPage-content'")
            ]

            for tipo, seletor, nome in SELETORES_ROBUSTOS:
                try:
                    print(f"      → Tentando seletor por: {nome}")
                    conteudo_div = WebDriverWait(driver, 3).until(EC.presence_of_element_located((tipo, seletor)))
                    texto_inteiro_teor = conteudo_div.text
                    if texto_inteiro_teor and len(texto_inteiro_teor.strip()) > 50:
                        print(f"      ✓ Conteúdo encontrado com sucesso!")
                        inteiro_teor_encontrado = True
                        break
                except TimeoutException:
                    continue
            
            if inteiro_teor_encontrado:
                caminho_arquivo = os.path.join(PASTA_SAIDA_TEXTOS, nome_arquivo)
                with open(caminho_arquivo, "w", encoding="utf-8") as f:
                    f.write(f"URL: {url}\n\n")
                    if texto_ementa: f.write(f"--- EMENTA ---\n{texto_ementa}\n\n")
                    if texto_fatos: f.write(f"--- FATOS ---\n{texto_fatos}\n\n")
                    f.write(f"--- INTEIRO TEOR ---\n{texto_inteiro_teor}")
                
                print(f"      ✅ Texto completo salvo em '{os.path.basename(caminho_arquivo)}'")
                log_entry['status'] = 'sucesso'
                log_entry['nome_arquivo_salvo'] = nome_arquivo
            else:
                print("      ❌ INTEIRO TEOR NÃO ENCONTRADO. Nenhum arquivo será salvo.")
                log_entry['status'] = 'erro_conteudo_nao_encontrado'
                log_entry['detalhe_erro'] = 'Nenhum dos seletores robustos encontrou o texto principal.'

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

        if LIMITE_SUCESSOS_SESSAO is not None and sucessos_nesta_sessao >= LIMITE_SUCESSOS_SESSAO:
            print(f"\n🛑 LIMITE DE {LIMITE_SUCESSOS_SESSAO} SUCESSOS ATINGIDO. Encerrando a raspagem.")
            parada_solicitada = True
        elif LIMITE_ERROS_SESSAO is not None and erros_nesta_sessao >= LIMITE_ERROS_SESSAO:
            print(f"\n🛑 LIMITE DE {LIMITE_ERROS_SESSAO} ERROS ATINGIDO. Encerrando a raspagem.")
            parada_solicitada = True

        if parada_solicitada: break
    
    if novos_registros:
        print(f"\n--- Fim da página {pagina_atual}. Salvando {len(novos_registros)} novos registros... ---")
        novos_df = pd.DataFrame(novos_registros)
        df_registro = pd.concat([df_registro, novos_df], ignore_index=True)
        salvar_progresso(df_registro)
        urls_processadas.update(novos_df['url'])
        novos_registros = []
    
    if parada_solicitada: break
    
    delay = random.uniform(4, 8)
    print(f"\n--- Pausa de {delay:.2f} segundos para evitar bloqueios ---")
    time.sleep(delay)

    pagina_atual += 1

# --- FIM DA EXECUÇÃO ---
print("\n🎉 Processo de raspagem concluído!")
driver.quit()