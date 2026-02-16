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

## 📁 Ficheiros a Modificar/Criar

### Backend
- [ ] `models.py` - Nova tabela `class_subject_link` com `grade_level`
- [ ] `schemas.py` - Novos schemas para disciplinas da turma
- [ ] `services/class_service.py` - Lógica de negócio para disciplinas/professores
- [ ] `api/v1/endpoints/classes.py` - Novos endpoints
- [ ] `alembic/versions/xxx_class_subject_link.py` - Migração

### Frontend
- [ ] `pages/ClassSubjects.jsx` - **NOVA** página de disciplinas da turma
- [ ] `pages/ClassDetails.jsx` - Adicionar link para ClassSubjects
- [ ] `hooks/useSchoolData.js` - Novos hooks para disciplinas da turma
- [ ] `App.jsx` - Nova rota `/courses/:courseId/classes/:classId/subjects`
- [ ] `components/DefaultLayout.jsx` - Remover link "Distribuição de Serviço"
- [ ] `pages/ServiceDistribution.jsx` - **APAGAR**
- [ ] `components/Forms/LessonForm.jsx` - **APAGAR** (será integrado na nova página)

---

## ✅ Tarefas Detalhadas

### Fase 1: Backend - Modelo de Dados
- [ ] 1.1 Criar tabela `class_subject_link` em `models.py`
  - Campos: `class_id`, `subject_id`, `grade_level`, `teacher_id` (nullable)
  - UniqueConstraint: `(class_id, subject_id, grade_level)`
- [ ] 1.2 Criar migração Alembic
- [ ] 1.3 Criar schemas em `schemas.py`:
  - `ClassSubjectCreate` (adicionar disciplina à turma)
  - `ClassSubjectRead` (ler disciplina com professor)
  - `ClassSubjectUpdate` (atribuir/alterar professor)
  - `ClassSubjectsListRead` (lista completa para a página)

### Fase 2: Backend - Endpoints
- [ ] 2.1 `GET /classes/{id}/subjects` - Lista disciplinas da turma (grade_level atual)
- [ ] 2.2 `POST /classes/{id}/subjects` - Adicionar disciplina à turma
- [ ] 2.3 `PATCH /classes/{id}/subjects/{subject_id}` - Atribuir/alterar professor
- [ ] 2.4 `DELETE /classes/{id}/subjects/{subject_id}` - Remover disciplina da turma
- [ ] 2.5 `GET /classes/{id}/available-subjects` - Disciplinas disponíveis (não associadas)
- [ ] 2.6 `GET /subjects/{id}/eligible-teachers` - Professores com competência na disciplina

### Fase 3: Backend - Validações
- [ ] 3.1 Validar que professor tem competência na disciplina (teacher_subject_link)
- [ ] 3.2 Validar que disciplina não está duplicada na turma/grade_level
- [ ] 3.3 Validar que disciplina pertence à organização

### Fase 4: Frontend - Nova Página
- [ ] 4.1 Criar `ClassSubjects.jsx` com:
  - Header da turma (nome, curso, grade_level)
  - Lista de disciplinas associadas com professor (ou "Sem professor")
  - Dropdown para atribuir professor (filtrado por competência)
  - Botão para adicionar nova disciplina
  - Botão para remover disciplina
- [ ] 4.2 Criar hooks em `useSchoolData.js`:
  - `useClassSubjects(classId)` - Lista disciplinas da turma
  - `useAvailableSubjects(classId)` - Disciplinas disponíveis para adicionar
  - `useEligibleTeachers(subjectId)` - Professores com competência
  - `useAddClassSubject()` - Mutation para adicionar
  - `useUpdateClassSubject()` - Mutation para atribuir professor
  - `useRemoveClassSubject()` - Mutation para remover

### Fase 5: Frontend - Integração
- [ ] 5.1 Adicionar rota em `App.jsx`: `/courses/:courseId/classes/:classId/subjects`
- [ ] 5.2 Adicionar link em `ClassDetails.jsx` para a nova página
- [ ] 5.3 Remover link "Distribuição de Serviço" do menu em `DefaultLayout.jsx`
- [ ] 5.4 Remover rota `/service-distribution` de `App.jsx`

### Fase 6: Limpeza
- [ ] 6.1 Apagar `ServiceDistribution.jsx`
- [ ] 6.2 Apagar `LessonForm.jsx` (lógica será integrada em ClassSubjects)
- [ ] 6.3 Verificar se há imports órfãos

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

**Alternativa descartada:** Usar `Lesson` diretamente
- Problema: Teria de criar Lesson sem todos os campos obrigatórios
- Problema: Misturar conceitos (atribuição vs necessidade de aula)

---

## 📝 Notas

- Grade_level atual da turma é calculado: `10 + (ano_atual - start_year)`
- Quando ano letivo muda, admin define novas disciplinas manualmente (automação futura)
- Professores só aparecem no dropdown se tiverem a disciplina em `teacher_subject_link`
