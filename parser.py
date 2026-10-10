import re
import pdfplumber
import psycopg2

# ==========================================
# 1. CONFIGURAÇÃO DA CONEXÃO AO POSTGRESQL
# ==========================================
# Altera "SUA_SENHA_AQUI" pela senha do teu PostgreSQL
DB_CONFIG = {
    "dbname": "acad_skilltree",
    "user": "postgres",
    "password": "1705",
    "host": "localhost",
    "port": "5432"
}

# Nome exato do ficheiro PDF na mesma pasta
PDF_PATH = "Currículo de Curso - Engenharia Elétrica - Eletrônica - Versão 2004_1.pdf"


def conectar_bd():
    """Abre a conexão com o banco de dados PostgreSQL."""
    return psycopg2.connect(**DB_CONFIG)


def executar_parser():
    print("--- Iniciando a leitura do PDF e povoamento do Banco de Dados ---")
    
    # Conecta ao PostgreSQL
    conn = conectar_bd()
    cursor = conn.cursor()

    # ------------------------------------------
    # PASSO A: Cadastrar o Curso
    # ------------------------------------------
    cursor.execute("""
        INSERT INTO curso (nome, versao, total_creditos, carga_horaria_total)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
    """, ("Engenharia Elétrica - Eletrônica", "2004/1", 234, 3825))
    
    curso_id = cursor.fetchone()[0]
    print(f"-> Curso cadastrado com ID: {curso_id}")

    disciplinas_extraidas = []
    mapa_pre_requisitos = {}  # { 'FTE029': ['FTE008'] }

    # ------------------------------------------
    # PASSO B: Ler as tabelas do PDF
    # ------------------------------------------
    with pdfplumber.open(PDF_PATH) as pdf:
        for num_pagina, pagina in enumerate(pdf.pages, start=1):
            tabelas = pagina.extract_tables()
            
            for tabela in tabelas:
                for linha in tabela:
                    # Ignorar linhas vazias ou de cabeçalho
                    if not linha or "COD." in linha or "PERÍODO" in linha or "PERIODO" in linha:
                        continue
                    
                    # Junta o texto da linha para identificar códigos com Expressão Regular (Regex)
                    texto_linha = " ".join([cell for cell in linha if cell]).strip()
                    
                    # Procura um código no formato de 3 a 4 letras + 3 números (ex: IEM011, FTE029)
                    match_codigo = re.search(r'\b([A-Z]{3,4}\d{3})\b', texto_linha)
                    if not match_codigo:
                        continue

                    codigo = match_codigo.group(1)
                    
                    # Extrair o período (coluna 0)
                    periodo_str = linha[0].strip() if linha[0] else ""
                    periodo = int(periodo_str) if periodo_str.isdigit() else None
                    
                    # Extrair Nome, Créditos e Carga Horária Total
                    nome = ""
                    creditos = 0
                    ch_total = 0
                    texto_prereq = ""

                    if len(linha) >= 4:
                        # Nome da disciplina
                        nome = linha[2].replace('\n', ' ').strip() if len(linha) > 2 and linha[2] else ""
                        
                        # Créditos
                        cred_str = linha[3].strip() if len(linha) > 3 and linha[3] else "0"
                        creditos = int(cred_str) if cred_str.isdigit() else 0
                        
                        # Carga Horária Total (geralmente penúltima ou antepenúltima coluna)
                        for celula in linha[4:]:
                            if celula and celula.strip().isdigit():
                                valor = int(celula.strip())
                                if valor >= 15:  # Filtra valores de carga horária reais
                                    ch_total = valor

                        # Texto dos Pré-requisitos (última coluna)
                        texto_prereq = linha[-1] if linha[-1] else ""

                    if codigo and nome:
                        disciplinas_extraidas.append({
                            "codigo": codigo,
                            "nome": nome,
                            "creditos": creditos,
                            "ch_total": ch_total,
                            "periodo": periodo
                        })

                        # Encontrar códigos de pré-requisitos no texto da última coluna
                        codigos_encontrados = re.findall(r'\b([A-Z]{3,4}\d{3})\b', texto_prereq)
                        # Remove o próprio código se capturado
                        codigos_encontrados = [c for c in codigos_encontrados if c != codigo]
                        
                        if codigos_encontrados:
                            mapa_pre_requisitos[codigo] = codigos_encontrados

    # ------------------------------------------
    # PASSO C: Inserir Disciplinas na Base de Dados
    # ------------------------------------------
    codigo_para_id = {}
    
    for disc in disciplinas_extraidas:
        cursor.execute("""
            INSERT INTO disciplina (curso_id, codigo, nome, creditos, carga_horaria_total, periodo_ideal)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id;
        """, (curso_id, disc["codigo"], disc["nome"], disc["creditos"], disc["ch_total"], disc["periodo"]))
        
        resultado = cursor.fetchone()
        if resultado:
            codigo_para_id[disc["codigo"]] = resultado[0]
        else:
            # Caso a disciplina já tenha sido inserida antes
            cursor.execute("SELECT id FROM disciplina WHERE codigo = %s AND curso_id = %s", (disc["codigo"], curso_id))
            res_existente = cursor.fetchone()
            if res_existente:
                codigo_para_id[disc["codigo"]] = res_existente[0]

    print(f"-> {len(codigo_para_id)} disciplinas salvas com sucesso.")

    # ------------------------------------------
    # PASSO D: Inserir a Árvore de Pré-requisitos
    # ------------------------------------------
    total_prereqs = 0
    for cod_disciplina, lista_requisitos in mapa_pre_requisitos.items():
        disc_id = codigo_para_id.get(cod_disciplina)
        
        for cod_requisito in lista_requisitos:
            req_id = codigo_para_id.get(cod_requisito)
            
            if disc_id and req_id:
                cursor.execute("""
                    INSERT INTO pre_requisito (disciplina_id, requisito_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                """, (disc_id, req_id))
                total_prereqs += 1

    print(f"-> {total_prereqs} conexões de pré-requisitos vinculadas.")

    # Salva as alterações e fecha a conexão
    conn.commit()
    cursor.close()
    conn.close()
    print("--- Processo concluído com sucesso! ---")


if __name__ == "__main__":
    executar_parser()