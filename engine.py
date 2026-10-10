import psycopg2

# 1. Configuração do Banco de Dados
DB_CONFIG = {
    "dbname": "acad_skilltree",
    "user": "postgres",
    "password": "1705", # Coloca a tua senha
    "host": "localhost",
    "port": "5432"
}

def conectar_bd():
    return psycopg2.connect(**DB_CONFIG)

def inicializar_aluno_teste(conn):
    """Cria um utilizador e o seu personagem de RPG para os testes."""
    cursor = conn.cursor()
    
    # Inserir o utilizador João Augusto
    cursor.execute("""
        INSERT INTO utilizador (nome, email, curso_id, periodo_atual)
        VALUES ('João Augusto', 'joao@ufam.edu.br', 1, 1)
        ON CONFLICT (email) DO UPDATE SET nome = EXCLUDED.nome
        RETURNING id;
    """)
    aluno_id = cursor.fetchone()[0]
    
    # Criar o personagem atrelado ao aluno
    cursor.execute("""
        INSERT INTO personagem (utilizador_id, nome, nivel, xp_total, xp_atual)
        VALUES (%s, 'Engenheiro Iniciante', 1, 0, 0)
        ON CONFLICT (utilizador_id) DO NOTHING;
    """, (aluno_id,))
    
    conn.commit()
    cursor.close()
    return aluno_id

def aprovar_materia(conn, aluno_id, codigo_materia):
    """Marca uma matéria como APROVADA no histórico."""
    cursor = conn.cursor()
    
    # Procura o ID da matéria pelo código (ex: 'IEM011')
    cursor.execute("SELECT id FROM disciplina WHERE codigo = %s", (codigo_materia,))
    resultado = cursor.fetchone()
    
    if resultado:
        disciplina_id = resultado[0]
        # Atualiza ou insere no histórico como APROVADO
        cursor.execute("""
            INSERT INTO historico_disciplina (utilizador_id, disciplina_id, status, semestre_cursado)
            VALUES (%s, %s, 'APROVADO', '2026/1')
            ON CONFLICT (utilizador_id, disciplina_id) 
            DO UPDATE SET status = 'APROVADO';
        """, (aluno_id, disciplina_id))
        conn.commit()
        print(f"[+] Matéria {codigo_materia} marcada como APROVADA!")
    
    cursor.close()

def calcular_xp_personagem(conn, aluno_id):
    """Calcula o XP baseado na carga horária das matérias aprovadas e sobe de nível."""
    cursor = conn.cursor()
    
    # Soma a carga horária total de todas as matérias aprovadas pelo aluno
    cursor.execute("""
        SELECT COALESCE(SUM(d.carga_horaria_total), 0)
        FROM historico_disciplina hd
        JOIN disciplina d ON hd.disciplina_id = d.id
        WHERE hd.utilizador_id = %s AND hd.status = 'APROVADO';
    """, (aluno_id,))
    
    carga_total_aprovada = cursor.fetchone()[0]
    
    # Regra de Gamificação: Cada hora de aula vale 15 XP
    xp_ganho = carga_total_aprovada * 15
    
    # Regra de Nível: Cada 500 XP = 1 Nível
    novo_nivel = (xp_ganho // 500) + 1
    
    # Atualiza o banco de dados do personagem
    cursor.execute("""
        UPDATE personagem 
        SET xp_total = %s, nivel = %s
        WHERE utilizador_id = %s
        RETURNING nome, nivel, xp_total;
    """, (xp_ganho, novo_nivel, aluno_id))
    
    personagem = cursor.fetchone()
    conn.commit()
    cursor.close()
    
    print(f"\n[STATUS DO PERSONAGEM]")
    print(f"Nome: {personagem[0]} | Nível: {personagem[1]} | XP Total: {personagem[2]}")

def verificar_materias_liberadas(conn, aluno_id):
    """Verifica na Árvore de Habilidades quais matérias já podem ser cursadas."""
    cursor = conn.cursor()
    
    # Lógica: Seleciona as disciplinas onde TODOS os pré-requisitos estão APROVADOS
    consulta_sql = """
        SELECT d.codigo, d.nome
        FROM disciplina d
        WHERE d.id NOT IN (
            -- Exclui matérias que o aluno já passou ou está a cursar
            SELECT disciplina_id FROM historico_disciplina WHERE utilizador_id = %s
        )
        AND NOT EXISTS (
            -- Verifica se existe algum pré-requisito que NÃO está aprovado
            SELECT 1
            FROM pre_requisito pr
            LEFT JOIN historico_disciplina hd 
              ON pr.requisito_id = hd.disciplina_id AND hd.utilizador_id = %s AND hd.status = 'APROVADO'
            WHERE pr.disciplina_id = d.id AND hd.id IS NULL
        )
        ORDER BY d.periodo_ideal ASC;
    """
    
    cursor.execute(consulta_sql, (aluno_id, aluno_id))
    liberadas = cursor.fetchall()
    
    print("\n[ÁRVORE DE HABILIDADES - MATÉRIAS DESBLOQUEADAS]")
    if liberadas:
        for mat in liberadas:
            print(f"- {mat[0]} : {mat[1]}")
    else:
        print("Nenhuma matéria nova libertada.")
        
    cursor.close()

if __name__ == "__main__":
    conexao = conectar_bd()
    
    print("--- INICIANDO MOTOR DO RPG ACADÉMICO ---")
    id_do_aluno = inicializar_aluno_teste(conexao)
    
    # Simulando o final do 1º Semestre: Passou em Cálculo 1 e Física 1!
    aprovar_materia(conexao, id_do_aluno, 'IEM011') # Cálculo I (90h)
    aprovar_materia(conexao, id_do_aluno, 'IEF028') # Física I E (60h)
    
    # Processa os sistemas
    calcular_xp_personagem(conexao, id_do_aluno)
    verificar_materias_liberadas(conexao, id_do_aluno)
    
    conexao.close()
    print("\n--- TESTE CONCLUÍDO ---")