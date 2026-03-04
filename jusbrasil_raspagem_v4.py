import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import os
import re
from datetime import datetime, timedelta
import pandas as pd
import random
import calendar

# --- CONFIGURAÇÕES GLOBAIS ---
# URL agora é um template com placeholders {date_from} e {date_to}
'''URL_TEMPLATE = "https://www.jusbrasil.com.br/jurisprudencia/busca?q=%22opera%C3%A7%C3%A3o+Lava+Jato%22&dateFrom={date_from}&dateTo={date_to}&tribunal=stf&tribunal=stj&tribunal=tj&tribunal=trf&tribunal=tse&tribunal=tre&tribunal=stm&tribunal=tjm&tribunal=tat_ms&tribunal=tat_sc&tribunal=tit_sp&tribunal=cat_go&tribunal=tnu&tribunal=tru&tribunal=cnj"

# Configurações de Data
DATA_INICIO_RASPAGEM = datetime(2020, 6, 6)
DATA_FIM_RASPAGEM = datetime.now() # Vai até o dia de hoje'''

URL_TEMPLATE = "https://www.jusbrasil.com.br/jurisprudencia/busca?q=%22opera%C3%A7%C3%A3o+Lava+Jato%22&dateFrom={date_from}&dateTo={date_to}&tribunal=stf"

# Configurações de Data (2021 a 2025)
DATA_INICIO_RASPAGEM = datetime(2021, 1, 1)
DATA_FIM_RASPAGEM = datetime(2025, 12, 31)

# --- MODOS DE PARADA CUSTOMIZADOS ---
# OBS: Este limite agora é POR MÊS. Se quiser raspar tudo, aumente este número.
NUMERO_MAXIMO_DE_PAGINAS_POR_MES = 50 
# Limites globais de segurança para a sessão inteira (todos os meses somados)
LIMITE_TOTAL_SUCESSOS = 1000 
LIMITE_TOTAL_ERROS = 50

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
        # print(f"💾 Progresso salvo.") # Comentado para reduzir poluição no terminal
    except Exception as e:
        print(f"🚨 ERRO AO SALVAR O PROGRESSO: {e}")

# --- INICIALIZAÇÃO DA BASE DE DADOS (PANDAS) ---
print("\n--- Carregando Base de Dados ---")
COLUNAS_REGISTRO = ['url', 'status', 'timestamp_processamento', 'nome_arquivo_salvo', 'ano_referencia', 'detalhe_erro']
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

# --- LOGIN INICIAL (FEITO APENAS UMA VEZ) ---
driver.get("https://www.jusbrasil.com.br")
print("\n" + "---" * 25)
print("⚠️ AÇÃO NECESSÁRIA - LOGIN ÚNICO ⚠️")
print("Faça o login no site do Jusbrasil agora. O script não pedirá mais login.")
input("Após o login, pressione ENTER aqui no terminal para começar a raspagem mês a mês...")
print("✅ Login confirmado. Iniciando a maratona de dados...")

# --- CONTADORES GLOBAIS DA SESSÃO ---
total_sucessos_sessao = 0
total_erros_sessao = 0
parada_global_solicitada = False

# ==============================================================================
# LOOP PRINCIPAL: CONTROLE DE DATAS (MÊS A MÊS)
# ==============================================================================
data_corrente = DATA_INICIO_RASPAGEM

while data_corrente < DATA_FIM_RASPAGEM and not parada_global_solicitada:
    # 1. Define início e fim do mês atual
    ano_atual = data_corrente.year
    mes_atual = data_corrente.month
    ultimo_dia_mes = calendar.monthrange(ano_atual, mes_atual)[1]
    
    date_from_str = data_corrente.strftime("%Y-%m-%d")
    data_fim_mes = datetime(ano_atual, mes_atual, ultimo_dia_mes)
    
    # Se o fim do mês for maior que hoje, limita até hoje
    if data_fim_mes > DATA_FIM_RASPAGEM:
        data_fim_mes = DATA_FIM_RASPAGEM
        
    date_to_str = data_fim_mes.strftime("%Y-%m-%d")
    
    print(f"\n" + "===" * 30)
    print(f"📅 INICIANDO PERÍODO: {date_from_str} até {date_to_str}")
    print("===" * 30)

    # 2. Monta a URL específica deste mês
    url_busca_mes = URL_TEMPLATE.format(date_from=date_from_str, date_to=date_to_str)

    # 3. Loop de paginação para este mês específico
    pagina_atual = 1
    while True:
        # Verificações de limites
        if NUMERO_MAXIMO_DE_PAGINAS_POR_MES and pagina_atual > NUMERO_MAXIMO_DE_PAGINAS_POR_MES:
            print(f"⏹️ Limite de páginas ({NUMERO_MAXIMO_DE_PAGINAS_POR_MES}) atingido para {mes_atual}/{ano_atual}. Indo para próximo mês.")
            break
        if LIMITE_TOTAL_SUCESSOS and total_sucessos_sessao >= LIMITE_TOTAL_SUCESSOS:
            print("\n🛑 LIMITE TOTAL DE SUCESSOS DA SESSÃO ATINGIDO. Encerrando tudo.")
            parada_global_solicitada = True
            break
        if LIMITE_TOTAL_ERROS and total_erros_sessao >= LIMITE_TOTAL_ERROS:
             print("\n🛑 LIMITE TOTAL DE ERROS DA SESSÃO ATINGIDO. Encerrando tudo.")
             parada_global_solicitada = True
             break

        print(f"\n--- 📅 {mes_atual}/{ano_atual} | Pág {pagina_atual} | Total Sucessos: {total_sucessos_sessao} ---")

        url_paginada = f"{url_busca_mes}&p={pagina_atual}"
        
        # --- Carregamento da Página de Busca ---
        pagina_carregada = False
        for tentativa in range(2):
            try:
                driver.get(url_paginada)
                # Espera por resultados OU pela mensagem de "nenhum resultado encontrado"
                WebDriverWait(driver, 20).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, 'div[class*="container-results"]') or 
                              d.find_element(By.XPATH, "//*[contains(text(), 'Nenhum resultado encontrado')]")
                )
                pagina_carregada = True
                break
            except Exception:
                if tentativa == 0:
                    time.sleep(5) # Breve pausa antes de tentar de novo
                else:
                    print(f"❌ Erro ao carregar pág {pagina_atual} de {mes_atual}/{ano_atual}.")

        if not pagina_carregada: break

        # Verifica se não há resultados para este mês/página
        if "Nenhum resultado encontrado" in driver.page_source:
             print(f"⏹️ Sem mais resultados para {mes_atual}/{ano_atual}.")
             break

        script_coleta = "return Array.from(document.querySelectorAll('h2[class*=\"shared-styles_title\"] a')).map(el => el.href);"
        urls_pagina = driver.execute_script(script_coleta)

        if not urls_pagina:
            print("⏹️ Fim da paginação para este mês.")
            break

        # --- Processamento dos Documentos ---
        novos_registros = []
        for i, url in enumerate(urls_pagina, 1):
            if parada_global_solicitada: break

            print(f" -> {i}/{len(urls_pagina)} (P{pagina_atual}-{mes_atual}/{ano_atual}): {url[:50]}...")

            if url in urls_processadas:
                print("    🟡 Já processado.")
                continue
            
            log_entry = {col: None for col in COLUNAS_REGISTRO}
            log_entry['url'] = url
            log_entry['timestamp_processamento'] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_entry['ano_referencia'] = ano_atual # Salva o ano no registro também

            try:
                driver.get(url)
                
                # -- Extração de Título --
                nome_arquivo = f"decisao_{ano_atual}_{mes_atual}_{i:03}.txt"
                titulo_doc = ""
                for seletor in [".document-title h1", 'div[class*="header_header"] h1']:
                    try:
                        el = WebDriverWait(driver, 4).until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor)))
                        titulo_doc = el.text
                        if titulo_doc:
                            nome_arquivo = f"{limpar_nome_arquivo(titulo_doc)}.txt"
                            break
                    except: continue

                # -- Extração de Ementa --
                texto_ementa = ""
                try:
                     el_ementa = driver.find_element(By.XPATH, "//h2[contains(., 'Ementa') or contains(., 'Resumo')]/following-sibling::*[1]")
                     texto_ementa = el_ementa.text
                except: pass

                # -- Extração de Inteiro Teor --
                texto_inteiro_teor = ""
                teor_encontrado = False
                
                # Tentativa de clique
                try:
                    btn_teor = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, "//*[(self::a or self::button) and contains(text(), 'Inteiro Teor')]")))
                    driver.execute_script("arguments[0].click();", btn_teor)
                    time.sleep(1.5)
                except: pass

                # Busca do texto
                seletores_teor = [
                    (By.XPATH, '//div[@data-doc-artifact="INTEIRO_TEOR"]'),
                    (By.CSS_SELECTOR, "div[class*='rich-text']"),
                    (By.CSS_SELECTOR, "div[class*='DocumentPage-content']")
                ]
                for tipo, seletor in seletores_teor:
                    try:
                        el_teor = WebDriverWait(driver, 3).until(EC.presence_of_element_located((tipo, seletor)))
                        texto_inteiro_teor = el_teor.text
                        if len(texto_inteiro_teor) > 50:
                            teor_encontrado = True
                            break
                    except: continue

                if teor_encontrado:
                    # === MUDANÇA PRINCIPAL DE PASTA ===
                    pasta_ano = os.path.join(PASTA_SAIDA_TEXTOS, str(ano_atual))
                    os.makedirs(pasta_ano, exist_ok=True)
                    caminho_final = os.path.join(pasta_ano, nome_arquivo)
                    # ==================================

                    with open(caminho_final, "w", encoding="utf-8") as f:
                        f.write(f"URL: {url}\nDATA_BUSCA_REF: {mes_atual}/{ano_atual}\n\n")
                        if texto_ementa: f.write(f"--- EMENTA ---\n{texto_ementa}\n\n")
                        f.write(f"--- INTEIRO TEOR ---\n{texto_inteiro_teor}")
                    
                    print(f"    ✅ Salvo em: {ano_atual}/{nome_arquivo[:30]}...")
                    log_entry['status'] = 'sucesso'
                    log_entry['nome_arquivo_salvo'] = os.path.join(str(ano_atual), nome_arquivo)
                    total_sucessos_sessao += 1
                else:
                    print("    ❌ Inteiro teor não encontrado.")
                    log_entry['status'] = 'erro_conteudo_nao_encontrado'
                    total_erros_sessao += 1

            except Exception as e:
                print(f"    🚨 Erro inesperado: {e}")
                log_entry['status'] = 'erro_inesperado'
                log_entry['detalhe_erro'] = str(e)
                total_erros_sessao += 1

            novos_registros.append(log_entry)
        
        # Salva progresso após cada página
        if novos_registros:
            df_new = pd.DataFrame(novos_registros)
            df_registro = pd.concat([df_registro, df_new], ignore_index=True)
            salvar_progresso(df_registro)
            urls_processadas.update(df_new['url'])

        pagina_atual += 1
        time.sleep(random.uniform(3, 6)) # Pausa entre páginas

    # --- FIM DO LOOP DO MÊS ---
    # Avança para o primeiro dia do próximo mês
    proximo_mes_data = (data_corrente.replace(day=28) + timedelta(days=4)).replace(day=1)
    data_corrente = proximo_mes_data
    
    if not parada_global_solicitada:
        print(f"⏳ Fim de {mes_atual}/{ano_atual}. Aguardando para iniciar próximo mês...")
        time.sleep(5) 

print("\n🎉 Processo de raspagem global concluído!")
driver.quit()