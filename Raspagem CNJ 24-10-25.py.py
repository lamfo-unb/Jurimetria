import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
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
PASTA_BASE_DE_DADOS = r"D:\OD\OneDrive - unb.br\Doutorado\Lamfo\Jurimetria\Py"
PASTA_SAIDA_TEXTOS = os.path.join(PASTA_BASE_DE_DADOS, "decisoes_salvas_pje")

ARQUIVO_REGISTRO_CSV = os.path.join(PASTA_BASE_DE_DADOS, "registro_processamento_pje.csv")
ARQUIVO_REGISTRO_XLSX = os.path.join(PASTA_BASE_DE_DADOS, "registro_processamento_pje.xlsx")

os.makedirs(PASTA_SAIDA_TEXTOS, exist_ok=True)
print(f"✅ O script está rodando a partir de: {os.getcwd()}")
print(f"📂 A base de dados e os arquivos serão salvos em: {os.path.abspath(PASTA_BASE_DE_DADOS)}")

# --- FUNÇÕES AUXILIARES ---
def limpar_nome_arquivo(titulo):
    titulo_limpo = re.sub(r'[\\/*?:"<>|.-]', "", titulo)
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
COLUNAS_REGISTRO = ['processo_numero', 'status', 'timestamp_processamento', 'nome_arquivo_salvo', 'detalhe_erro']
try:
    df_registro = pd.read_csv(ARQUIVO_REGISTRO_CSV)
    print(f"📖 Base de dados encontrada. {len(df_registro)} registros carregados.")
except FileNotFoundError:
    df_registro = pd.DataFrame(columns=COLUNAS_REGISTRO)
    print("📖 Nenhuma base de dados encontrada. Um novo arquivo será criado.")

processos_processados = set(df_registro['processo_numero'])

# --- INICIALIZAÇÃO DO NAVEGADOR ---
options = uc.ChromeOptions()
options.add_argument('--start-maximized')
print("\nIniciando navegador com undetected-chromedriver...")
driver = uc.Chrome(options=options)

# --- EXECUÇÃO PRINCIPAL ---
sucessos_nesta_sessao = 0
erros_nesta_sessao = 0
parada_solicitada = False
pagina_atual = 1

print(f"Carregando página de busca inicial: {URL_BASE_BUSCA}")
driver.get(URL_BASE_BUSCA)

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
    
    novos_registros = []

    try:
        # Primeiro, esperamos que as abas (tabs) estejam visíveis
        seletor_abas = "//div[@role='tab']"
        WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.XPATH, seletor_abas)))
        
        # Contamos quantas abas existem para criar o loop
        num_abas = len(driver.find_elements(By.XPATH, seletor_abas))
        print(f"🔍 {num_abas} abas de tribunais encontradas nesta página.")

    except TimeoutException:
        print(f"❌ ERRO CRÍTICO: Nenhuma aba de tribunal foi encontrada na página {pagina_atual}. Encerrando.")
        break

    # ==============================================================================
    # NOVA LÓGICA: LOOP INTERNO PARA PERCORRER AS ABAS
    # ==============================================================================
    for i in range(num_abas):
        if parada_solicitada: break
        
        try:
            # Reencontramos as abas a cada iteração para evitar o erro "StaleElementReferenceException"
            abas_da_pagina = driver.find_elements(By.XPATH, seletor_abas)
            aba_atual = abas_da_pagina[i]
            
            nome_aba = aba_atual.text.split('\n')[0] if '\n' in aba_atual.text else aba_atual.text
            print(f"\n   -> Processando aba {i+1}/{num_abas}: '{nome_aba}'")
            
            # Clica na aba
            aba_atual.click()
            time.sleep(2) # Pausa para o conteúdo da aba carregar

            # Agora, extraímos o conteúdo do artigo visível
            artigo = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, "//article"))
            )
            
            log_entry = {col: None for col in COLUNAS_REGISTRO}
            numero_processo = ""
            
            # Extrai o número do processo como identificador único
            seletor_processo = ".//div[starts-with(normalize-space(.), 'Processo')]"
            elemento_processo = artigo.find_element(By.XPATH, seletor_processo)
            texto_processo_completo = elemento_processo.text
            numero_processo = texto_processo_completo.replace("Processo", "").strip()
            log_entry['processo_numero'] = numero_processo

            print(f"      -> Documento: {numero_processo}")
            
            if numero_processo in processos_processados:
                print("      -> 🟡 Documento já consta na base de dados. Pulando.")
                continue

            # Extrai o texto completo do artigo
            texto_completo = artigo.text
            nome_arquivo = f"{limpar_nome_arquivo(numero_processo)}.txt"
            caminho_arquivo = os.path.join(PASTA_SAIDA_TEXTOS, nome_arquivo)

            with open(caminho_arquivo, "w", encoding="utf-8") as f:
                f.write(texto_completo)

            print(f"      ✅ Texto completo salvo em '{os.path.basename(caminho_arquivo)}'")
            log_entry['status'] = 'sucesso'
            log_entry['nome_arquivo_salvo'] = nome_arquivo
            log_entry['timestamp_processamento'] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            sucessos_nesta_sessao += 1
            novos_registros.append(log_entry)

        except StaleElementReferenceException:
            print("      ⚠️ Erro de elemento 'stale' ao tentar processar a aba. Tentando novamente na próxima iteração.")
            time.sleep(3) # Pausa extra
            continue # Tenta a proxima aba
        except Exception as e:
            print(f"      ❌ Erro INESPERADO ao processar a aba '{nome_aba}': {e}")
            erros_nesta_sessao += 1
            if 'log_entry' in locals() and log_entry.get('processo_numero'):
                log_entry['status'] = 'erro_inesperado'
                log_entry['detalhe_erro'] = str(e).replace('\n', ' ')
                novos_registros.append(log_entry)

        if (LIMITE_SUCESSOS_SESSAO and sucessos_nesta_sessao >= LIMITE_SUCESSOS_SESSAO) or \
           (LIMITE_ERROS_SESSAO and erros_nesta_sessao >= LIMITE_ERROS_SESSAO):
            print(f"\n🛑 LIMITE DE SUCESSOS/ERROS ATINGIDO. Encerrando a raspagem.")
            parada_solicitada = True
    
    # Após processar todas as abas, salvamos o progresso da página inteira
    if novos_registros:
        print(f"\n--- Fim da página {pagina_atual}. Salvando {len(novos_registros)} novos registros... ---")
        novos_df = pd.DataFrame(novos_registros)
        df_registro = pd.concat([df_registro, novos_df], ignore_index=True)
        salvar_progresso(df_registro)
        processos_processados.update(novos_df['processo_numero'].dropna())
    
    if parada_solicitada: break

    try:
        print("\n--- Navegando para a próxima página ---")
        seletor_proxima_pagina = "/html/body/app-root/uikit-layout/mat-sidenav-container/mat-sidenav-content/div[2]/app-consulta/div/div/div[2]/app-resultado/div[2]/div/div/div/p-paginator/div/a[3]"
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