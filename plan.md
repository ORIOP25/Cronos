# Plano: Gestão de Professores Curso-Cêntrica

## 📋 Resumo do Problema

Atualmente a atribuição de professores a turmas é feita numa página separada (`ServiceDistribution.jsx`). É necessário:
1. **Eliminar** a página de Distribuição de Serviço
2. **Criar** nova página de disciplinas por turma (`ClassSubjects.jsx`)
3. **Implementar** modelo onde disciplinas são definidas por turma/grade_level
4. **Filtrar** professores por competência (só aparecem os que podem lecionar a disciplina)

---

## 🎯 Modelo de Dados

```
Turma TGEI 26/29 (grade_level=10 atualmente)
│
└── grade_level=10 (ano letivo 26/27):
    ├── Português → Prof. Ana ✅
    ├── Matemática → Prof. Silva ✅
    └── Programação I → (sem professor) ⏳

Quando grade_level mudar para 11:
- Disciplinas e professores do 10º ficam como histórico
- Admin define novas disciplinas para o 11º
```

**Regras:**
- Disciplinas são associadas à turma + grade_level
- Um professor só pode ser atribuído a uma disciplina se tiver essa competência
- Uma disciplina da turma só pode ter 1 professor
- Quando grade_level muda, atribuições anteriores ficam como histórico

---

## 📁 Ficheiros Modificados/Criados

### Backend
- [x] `models.py` - Nova tabela `ClassSubjectLink` com `grade_level`
- [x] `schemas.py` - Novos schemas para disciplinas da turma
- [x] `services/class_service.py` - Lógica de negócio para disciplinas/professores
- [x] `api/v1/endpoints/classes.py` - Novos endpoints
- [x] `alembic/versions/f8a3b2c1d4e5_add_class_subject_link_table.py` - Migração

### Frontend
- [x] `pages/ClassSubjects.jsx` - **NOVA** página de disciplinas da turma
- [x] `pages/ClassDetails.jsx` - Adicionado link para ClassSubjects
- [x] `hooks/useSchoolData.js` - Novos hooks para disciplinas da turma
- [x] `App.jsx` - Nova rota `/courses/:courseId/classes/:classId/subjects`
- [x] `components/DefaultLayout.jsx` - Removido link "Distribuição de Serviço"
- [x] `pages/ServiceDistribution.jsx` - Deprecado (redireciona para /courses)
- [x] `components/Forms/LessonForm.jsx` - Deprecado

---

## ✅ Tarefas Concluídas

### Fase 1: Backend - Modelo de Dados ✅
- [x] 1.1 Criar tabela `class_subject_link` em `models.py`
- [x] 1.2 Criar migração Alembic
- [x] 1.3 Criar schemas em `schemas.py`

### Fase 2: Backend - Endpoints ✅
- [x] 2.1 `GET /classes/{id}/subjects`
- [x] 2.2 `POST /classes/{id}/subjects`
- [x] 2.3 `PATCH /classes/{id}/subjects/{subject_id}`
- [x] 2.4 `DELETE /classes/{id}/subjects/{subject_id}`
- [x] 2.5 `GET /classes/{id}/available-subjects`
- [x] 2.6 `GET /classes/subjects/{id}/eligible-teachers`

### Fase 3: Backend - Validações ✅
- [x] 3.1 Validar competência do professor
- [x] 3.2 Validar disciplina não duplicada
- [x] 3.3 Validar disciplina pertence à org

### Fase 4: Frontend - Nova Página ✅
- [x] 4.1 Criar `ClassSubjects.jsx`
- [x] 4.2 Criar hooks em `useSchoolData.js`

### Fase 5: Frontend - Integração ✅
- [x] 5.1-5.4 Rotas e menu

### Fase 6: Limpeza ✅
- [x] 6.1-6.3 Ficheiros deprecados

### Fase 7: Testes
- [ ] 7.1 Testar fluxo completo: Curso → Turma → Disciplinas → Atribuir Professor
- [ ] 7.2 Testar filtro de professores por competência
- [ ] 7.3 Testar adicionar/remover disciplinas
- [ ] 7.4 Verificar que menu não tem mais "Distribuição de Serviço"

---

## 🔄 Decisão sobre tabela Lesson

**Opção escolhida:** Usar nova tabela `class_subject_link` em vez de modificar `Lesson`

**Razão:** 
- `Lesson` é usada pelo Solver para gerar horários (tem `num_per_week`, `is_double`)
- A nova tabela é apenas para definir "que disciplinas a turma tem e quem leciona"
- Quando o Solver correr, pode criar `Lesson` baseado em `class_subject_link`

---

## 📝 Próximos Passos

1. **Correr migração:** `alembic upgrade head`
2. **Testar backend:** Verificar endpoints com Postman/curl
3. **Testar frontend:** Navegar Curso → Turma → Disciplinas
4. **Apagar ficheiros deprecados:** ServiceDistribution.jsx, LessonForm.jsx
