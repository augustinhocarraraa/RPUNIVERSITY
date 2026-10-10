from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2

app = FastAPI(title="RPG Académico API", description="API para gerir a Skill Tree da Graduação")

# 1. Configuração da Base de Dados
DB_CONFIG = {
    "dbname": "acad_skilltree",
    "user": "postgres",
    "password": "1705",  # <-- Coloca a tua palavra-passe aqui
    "host": "localhost",
    "port": "5432"
}

def conectar_bd():
    return psycopg2.connect(**DB_CONFIG)

# Modelo de dados para receber no POST (quando o aluno aprova uma matéria)
class AprovarMateriaRequest(BaseModel):
    codigo_materia: str

# ---------------------------------------------------------
# ROTAS DA API
# ---------------------------------------------------------

@app.get("/")
def home():
    return {"mensagem": "API do RPG Académico está a correr perfeitamente!"}

@app.get("/aluno/{aluno_id}/status")
def obter_status_personagem(aluno_id: int):
    """Retorna o Nível e XP atual do aluno."""
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT nome, nivel, xp_total, xp_atual 
            FROM personagem WHERE utilizador_id = %s
        """, (aluno_id,))
        
        resultado = cursor.fetchone()
        conn.close()
        
        if not resultado:
            raise HTTPException(status_code=404, detail="Personagem não encontrado")
            
        return {
            "classe": resultado[0],
            "nivel": resultado[1],
            "xp_total": resultado[2]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/aluno/{aluno_id}/arvore-habilidades")
def obter_materias_liberadas(aluno_id: int):
    """Retorna a lista de matérias que o aluno já desbloqueou para cursar."""
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        
        consulta = """
            SELECT d.codigo, d.nome, d.creditos
            FROM disciplina d
            WHERE d.id NOT IN (
                SELECT disciplina_id FROM historico_disciplina WHERE utilizador_id = %s
            )
            AND NOT EXISTS (
                SELECT 1 FROM pre_requisito pr
                LEFT JOIN historico_disciplina hd 
                  ON pr.requisito_id = hd.disciplina_id AND hd.utilizador_id = %s AND hd.status = 'APROVADO'
                WHERE pr.disciplina_id = d.id AND hd.id IS NULL
            )
            ORDER BY d.periodo_ideal ASC;
        """
        cursor.execute(consulta, (aluno_id, aluno_id))
        materias = cursor.fetchall()
        conn.close()
        
        lista_formatada = [{"codigo": m[0], "nome": m[1], "creditos": m[2]} for m in materias]
        return {"materias_desbloqueadas": lista_formatada}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/aluno/{aluno_id}/aprovar")
def aprovar_materia(aluno_id: int, request: AprovarMateriaRequest):
    """Marca uma matéria como aprovada e recalcula o XP do aluno."""
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        
        # 1. Verifica se a matéria existe
        cursor.execute("SELECT id FROM disciplina WHERE codigo = %s", (request.codigo_materia,))
        res_disc = cursor.fetchone()
        if not res_disc:
            conn.close()
            raise HTTPException(status_code=404, detail="Matéria não encontrada")
            
        disciplina_id = res_disc[0]
        
        # 2. Aprova a matéria no histórico
        cursor.execute("""
            INSERT INTO historico_disciplina (utilizador_id, disciplina_id, status)
            VALUES (%s, %s, 'APROVADO')
            ON CONFLICT (utilizador_id, disciplina_id) 
            DO UPDATE SET status = 'APROVADO';
        """, (aluno_id, disciplina_id))
        
        # 3. Recalcula o XP (15 XP por cada hora aprovada)
        cursor.execute("""
            SELECT COALESCE(SUM(d.carga_horaria_total), 0)
            FROM historico_disciplina hd
            JOIN disciplina d ON hd.disciplina_id = d.id
            WHERE hd.utilizador_id = %s AND hd.status = 'APROVADO';
        """, (aluno_id,))
        carga_total = cursor.fetchone()[0]
        
        novo_xp = carga_total * 15
        novo_nivel = (novo_xp // 500) + 1
        
        # 4. Atualiza o personagem
        cursor.execute("""
            UPDATE personagem SET xp_total = %s, nivel = %s WHERE utilizador_id = %s
        """, (novo_xp, novo_nivel, aluno_id))
        
        conn.commit()
        conn.close()
        
        return {
            "mensagem": f"Matéria {request.codigo_materia} aprovada com sucesso!",
            "novo_nivel": novo_nivel,
            "novo_xp": novo_xp
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))