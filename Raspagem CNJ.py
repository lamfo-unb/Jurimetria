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
URL_BASE_BUSCA = "https://comunica.pje.jus.br/consulta?texto=%22opera%C3%A7%C3%A3o%20lava-jato%22&dataDisponibilizacaoInicio=2015-01-01&dataDisponibilizacaoFim=2025-12-31"

# --- MODOS DE PARADA CUSTOMIZADOS ---
# ATUALIZADO CONFORME SOLICITADO
NUMERO_MAXIMO_DE_PAGINAS = 10000
LIMITE_SUCESSOS_SESSAO = 50000
LIMITE_ERROS_SESSAO = 500

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
    # ==============================================================================
    # ATUALIZADO CONFORME SOLICITADO
    # 1. Substitui pontos por underline
    titulo_limpo = titulo.replace(".", "_")
    # 2. Remove caracteres inválidos (MANTÉM HÍFEN E UNDERLINE)
    titulo_limpo = re.sub(r'[\\/*?:"<>|]', "", titulo_limpo)
    # 3. Substitui espaços por underline
    titulo_limpo = re.sub(r'\s+', '_', titulo_limpo)
    # ==============================================================================
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
print("✅ Ok, continuando a execution...")

while True:
    if NUMERO_MAXIMO_DE_PAGINAS and pagina_atual > NUMERO_MAXIMO_DE_PAGINAS:
        print(f"\n🛑 Limite de {NUMERO_MAXIMO_DE_PAGINAS} páginas atingido. Encerrando.")
        break

    print(f"\n" + "---" * 25)
    print(f"--- 📄 Página {pagina_atual} | Sucessos: {sucessos_nesta_sessao} | Erros: {erros_nesta_sessao} ---")
    print("---" * 25)
    
    novos_registros = []
    seletor_artigos = "//article"

    try:
        # 1. TENTA ENCONTRAR ABAS
        seletor_abas = "//div[@role='tab']"
        WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.XPATH, seletor_abas)))
        
        num_abas = len(driver.find_elements(By.XPATH, seletor_abas))
        print(f"🔍 {num_abas} abas de tribunais encontradas nesta página.")
        
        # SE ENCONTRAR ABAS, FAZ O LOOP DE ABAS
        for i in range(num_abas):
            if parada_solicitada: break
            
            try:
                abas_da_pagina = driver.find_elements(By.XPATH, seletor_abas)
                aba_atual = abas_da_pagina[i]
                
                # ==============================================================================
                # Pega o nome da aba para usar no nome do arquivo
                nome_aba = aba_atual.text.split('\n')[0] if '\n' in aba_atual.text else aba_atual.text
                nome_tribunal_limpo = limpar_nome_arquivo(nome_aba)
                # ==============================================================================
                
                print(f"\n   -> Processando aba {i+1}/{num_abas}: '{nome_aba}'")
                aba_atual.click()
                
                WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, seletor_artigos))
                )
                time.sleep(1)

                artigos_na_aba = driver.find_elements(By.XPATH, seletor_artigos)
                print(f"      -> {len(artigos_na_aba)} documentos encontrados nesta aba.")

                for j, artigo in enumerate(artigos_na_aba, 1):
                    log_entry, numero_processo = {}, ""
                    try:
                        log_entry = {col: None for col in COLUNAS_REGISTRO}
                        seletor_processo = ".//div[starts-with(normalize-space(.), 'Processo')]"
                        elemento_processo = artigo.find_element(By.XPATH, seletor_processo)
                        
                        # ==============================================================================
                        # ATUALIZADO CONFORME SOLICITADO
                        # Pega apenas a primeira linha do texto para evitar "Imprimir..."
                        texto_processo_completo = elemento_processo.text
                        primeira_linha = texto_processo_completo.split('\n')[0]
                        numero_processo = primeira_linha.replace("Processo", "").strip()
                        # ==============================================================================
                        
                        log_entry['processo_numero'] = numero_processo
                        print(f"         -> Processando doc {j}/{len(artigos_na_aba)}: {numero_processo}")
                        
                        if numero_processo in processos_processados:
                            print("            -> 🟡 Documento já consta na base de dados. Pulando.")
                            continue

                        texto_completo = artigo.text
                        
                        # ==============================================================================
                        # ATUALIZADO CONFORME SOLICITADO
                        # Novo formato de nome de arquivo: TRIBUNAL_NUMERO-PROCESSO.txt
                        nome_processo_limpo = limpar_nome_arquivo(numero_processo)
                        nome_arquivo = f"{nome_tribunal_limpo}_{nome_processo_limpo}.txt"
                        # ==============================================================================
                        
                        caminho_arquivo = os.path.join(PASTA_SAIDA_TEXTOS, nome_arquivo)

                        with open(caminho_arquivo, "w", encoding="utf-8") as f: f.write(texto_completo)

                        print(f"            -> ✅ Texto completo salvo em '{os.path.basename(caminho_arquivo)}'")
                        log_entry['status'] = 'sucesso'
                        log_entry['nome_arquivo_salvo'] = nome_arquivo
                        sucessos_nesta_sessao += 1

                    except Exception as e_artigo:
                        print(f"         -> ❌ Erro ao processar um documento específico ({numero_processo}): {e_artigo}")
                        erros_nesta_sessao += 1
                        log_entry['status'] = 'erro_processamento_artigo'
                        log_entry['detalhe_erro'] = str(e_artigo).replace('\n', ' ')
                    
                    log_entry['timestamp_processamento'] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    novos_registros.append(log_entry)
                    
                    if (LIMITE_SUCESSOS_SESSAO and sucessos_nesta_sessao >= LIMITE_SUCESSOS_SESSAO) or \
                       (LIMITE_ERROS_SESSAO and erros_nesta_sessao >= LIMITE_ERROS_SESSAO):
                        print(f"\n🛑 LIMITE DE SUCESSOS/ERROS ATINGIDO. Encerrando a raspagem.")
                        parada_solicitada = True
                        break
            
            except StaleElementReferenceException:
                print("      ⚠️ Erro de elemento 'stale' ao tentar processar a aba. Pulando para próxima aba.")
                time.sleep(3) 
                continue 
            except Exception as e_aba:
                print(f"      ❌ Erro INESPERADO ao processar a aba: {e_aba}")
                erros_nesta_sessao += 1
    
    except TimeoutException:
        # 2. SE NÃO ENCONTRAR ABAS (FALLBACK)
        print(f"      -> ⚠️ Nenhuma aba encontrada na página {pagina_atual}. Processando como página simples.")
        
        try:
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, seletor_artigos))
            )
            artigos_na_pagina = driver.find_elements(By.XPATH, seletor_artigos)
            print(f"      -> {len(artigos_na_pagina)} documentos encontrados nesta página.")

            if not artigos_na_pagina:
                print("      -> ⚠️ Nenhum documento (article) encontrado nesta página. Pulando para a próxima.")

            for j, artigo in enumerate(artigos_na_pagina, 1):
                log_entry, numero_processo = {}, ""
                try:
                    log_entry = {col: None for col in COLUNAS_REGISTRO}
                    seletor_processo = ".//div[starts-with(normalize-space(.), 'Processo')]"
                    elemento_processo = artigo.find_element(By.XPATH, seletor_processo)
                    
                    # ==============================================================================
                    # ATUALIZADO CONFORME SOLICITADO (igual ao bloco de abas)
                    texto_processo_completo = elemento_processo.text
                    primeira_linha = texto_processo_completo.split('\n')[0]
                    numero_processo = primeira_linha.replace("Processo", "").strip()
                    # ==============================================================================
                    
                    log_entry['processo_numero'] = numero_processo
                    print(f"         -> Processando doc {j}/{len(artigos_na_pagina)}: {numero_processo}")
                    
                    if numero_processo in processos_processados:
                        print("            -> 🟡 Documento já consta na base de dados. Pulando.")
                        continue

                    texto_completo = artigo.text

                    # ==============================================================================
                    # ATUALIZADO CONFORME SOLICITADO (igual ao bloco de abas)
                    nome_tribunal_limpo = "PAGINA_SEM_ABA" # Prefixo padrão para fallback
                    nome_processo_limpo = limpar_nome_arquivo(numero_processo)
                    nome_arquivo = f"{nome_tribunal_limpo}_{nome_processo_limpo}.txt"
                    # ==============================================================================

                    caminho_arquivo = os.path.join(PASTA_SAIDA_TEXTOS, nome_arquivo)

                    with open(caminho_arquivo, "w", encoding="utf-8") as f: f.write(texto_completo)

                    print(f"            -> ✅ Texto completo salvo em '{os.path.basename(caminho_arquivo)}'")
                    log_entry['status'] = 'sucesso'
                    log_entry['nome_arquivo_salvo'] = nome_arquivo
                    sucessos_nesta_sessao += 1

                except Exception as e_artigo:
                    print(f"         -> ❌ Erro ao processar um documento específico ({numero_processo}): {e_artigo}")
                    erros_nesta_sessao += 1
                    log_entry['status'] = 'erro_processamento_artigo'
                    log_entry['detalhe_erro'] = str(e_artigo).replace('\n', ' ')
                
                log_entry['timestamp_processamento'] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                novos_registros.append(log_entry)

                if (LIMITE_SUCESSOS_SESSAO and sucessos_nesta_sessao >= LIMITE_SUCESSOS_SESSAO) or \
                   (LIMITE_ERROS_SESSAO and erros_nesta_sessao >= LIMITE_ERROS_SESSAO):
                    print(f"\n🛑 LIMITE DE SUCESSOS/ERROS ATINGIDO. Encerrando a raspagem.")
                    parada_solicitada = True
                    break

        except TimeoutException:
             print("      -> ❌ Nenhum documento (article) encontrado nesta página simples. Pulando para a próxima.")
        except Exception as e_page:
            print(f"      ❌ Erro INESPERADO ao processar a página simples: {e_page}")
            erros_nesta_sessao += 1

    # 3. APÓS PROCESSAR (COM OU SEM ABAS), SALVA E VAI PARA A PRÓXIMA PÁGINA
    if novos_registros:
        print(f"\n--- Fim da página {pagina_atual}. Salvando {len(novos_registros)} novos registros... ---")
        novos_df = pd.DataFrame(novos_registros)
        df_registro = pd.concat([df_registro, novos_df], ignore_index=True)
        salvar_progresso(df_registro)
        processos_processados.update(novos_df['processo_numero'].dropna())
    
    if parada_solicitada: break

    try:
        print("\n--- Navegando para a próxima página ---")
        seletor_proxima_pagina = "//a[contains(@class, 'ui-paginator-next') and not(contains(@class, 'ui-state-disabled'))]"
        
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
driver.quit()

