import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '../../ApiClientContext'
import { invalidatePreparationQueries } from '../readiness/data'
import { invalidateOrgQueries, orgQueryKey } from '../queryKeys'
import { useOrganization, useAuth } from '@clerk/react'
import { addDays } from '../../utils/formatUtils'

const STATIC_OPTS = {
  staleTime: 1000 * 60 * 30,
  refetchOnWindowFocus: false,
}

export const useRooms = () => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('rooms', orgId),
    queryFn: async () => {
      return apiClient.get('/rooms/')
    },
    enabled: Boolean(orgId),
    ...STATIC_OPTS
  })
}

export const useSubjects = () => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('subjects', orgId),
    queryFn: async () => {
      return apiClient.get('/subjects/')
    },
    enabled: Boolean(orgId),
    ...STATIC_OPTS
  })
}

export const useClasses = ({ enabled = true } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('classes', orgId),
    queryFn: async () => {
      return apiClient.get('/classes/')
    },
    enabled: Boolean(orgId) && enabled,
    ...STATIC_OPTS
  })
}


export const useTimeslots = ({ onDate } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: onDate ? orgQueryKey('timeslots', orgId, 'date', onDate) : orgQueryKey('timeslots', orgId),
    queryFn: async () => {
      return onDate ? apiClient.get('/timeslots/', { params: { on_date: onDate } }) : apiClient.get('/timeslots/')
    },
    enabled: Boolean(orgId) && isLoaded,
  })
}

export const useWeekGridVersions = (weekStart) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: orgQueryKey('timeslots', orgId, 'range', weekStart),
    queryFn: async () => {
      return apiClient.get('/timeslots/range', {
        params: { from_date: weekStart, to_date: addDays(weekStart, 6) },
      })
    },
    enabled: Boolean(orgId) && isLoaded && Boolean(weekStart),
  })
}

// --- CURSOS ---
export const useCourses = () => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('courses', orgId),
    queryFn: async () => {
      return apiClient.get('/courses/')
    },
    enabled: Boolean(orgId),
    ...STATIC_OPTS
  })
}

// --- CURRÍCULO DA TURMA (Dados Relacionados) ---


// --- HOOKS OPERACIONAIS (Dinâmicos) ---


// ==========================================
//  HOOKS DE MUTAÇÃO GENÉRICOS (CRUD Factory)
//  Estes hooks gerem a escrita e a atualização automática da cache.
// ==========================================

/**
 * Cria uma nova entidade.
 * @param {string} entityKey - O nome da entidade (ex: 'rooms'). Define o URL e a Cache Key.
 */
const useCreateEntity = (entityKey, dependentRoots = []) => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (newItem) => {
      return apiClient.post(`/${entityKey}/`, newItem)
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, [entityKey, ...dependentRoots])
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}

/**
 * Atualiza uma entidade existente.
 * Uso: mutate({ id: 1, name: "Novo Nome" })
 * 
 * PATCH: Atualização parcial (apenas campos enviados)
 */
const useUpdateEntity = (entityKey, dependentRoots = []) => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ id, ...updateData }) => {
      return apiClient.patch(`/${entityKey}/${id}`, updateData)
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, [entityKey, ...dependentRoots])
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}

/**
 * Apaga uma entidade.
 * Uso: mutate(1)
 */
const useDeleteEntity = (entityKey, dependentRoots = []) => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (id) => {
      return apiClient.delete(`/${entityKey}/${id}`)
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, [entityKey, ...dependentRoots])
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}

export const useCreateRoom = () => useCreateEntity('rooms')
export const useUpdateRoom = () => useUpdateEntity('rooms')
export const useDeleteRoom = () => useDeleteEntity('rooms')
export const useCreateSubject = () => useCreateEntity('subjects', ['courses'])
export const useUpdateSubject = () => useUpdateEntity('subjects', ['courses'])
export const useDeleteSubject = () => useDeleteEntity('subjects', ['courses'])
export const useCreateCourse = () => useCreateEntity('courses')

// ==========================================
//  FASE 4: GESTÃO DE CURSOS
//  Hooks específicos para operações de cursos com hierarchia (Course → Class)
// ==========================================

/**
 * Obter detalhes completos de um curso (Dashboard).
 * 
 * 4º Pilares:
 * - Optimization: Cache separada por courseId, staleTime 5min (dados semi-estáticos)
 * - Scalability: enabled flag previne queries desnecessárias
 * - Stability: Retorna subjects + classes de uma vez (évita N+1)
 * 
 * Uso:
 * const { data: course, isLoading } = useCourseDetails(5)
 * course.subjects[0].name
 * course.classes[0].name
 */
export const useCourseDetails = (courseId) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('courses', orgId, courseId),
    queryFn: async () => {
      return apiClient.get(`/courses/${courseId}`)
    },
    enabled: Boolean(orgId) && Boolean(courseId),
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
}

/**
 * Atualizar curso (PATCH - apenas campos enviados).
 * 
 * 4º Pilares:
 * - Security: Backend valida abbreviation uniqueness
 * - Stability: PATCH permite atualizações parciais sem risco de sobrescrever
 * - Optimization: Invalida caches específicas (listagem + detalhe)
 * 
 * Uso:
 * const updateCourse = useUpdateCourse()
 * updateCourse.mutate({
 *   courseId: 5,
 *   data: { name: "Novo Nome", subject_ids: [1, 2, 3] }
 * })
 */
export const useUpdateCourse = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, data }) => {
      return apiClient.patch(`/courses/${courseId}`, data)
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, ['courses'])
    }
  })
}

/**
 * Apagar curso com validação de dependências.
 * 
 * 4º Pilares:
 * - Stability: Backend rejeita se há classes (impede perda de dados)
 * - Security: Validação no servidor, frontend apenas consome resposta
 * 
 * Uso:
 * const deleteCourse = useDeleteCourse()
 * deleteCourse.mutate(5) // courseId
 */
export const useDeleteCourse = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (courseId) => {
      return apiClient.delete(`/courses/${courseId}`)
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, ['courses'])
    }
  })
}


export const useCreateCourseClass = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, data }) => {
      return apiClient.post(`/courses/${courseId}/classes`, data)
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, ['courses', 'classes'])
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}


export const useUpdateCourseClass = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, classId, data }) => {
      return apiClient.patch(`/courses/${courseId}/classes/${classId}`, data)
    },
    onSuccess: (data, variables) => {
      void invalidateOrgQueries(queryClient, orgId, ['courses', 'classes'])
      void invalidatePreparationQueries(queryClient, orgId)
      queryClient.setQueryData(orgQueryKey('classes', orgId, variables.classId), (previous) => (
        previous ? { ...previous, ...data } : previous
      ))
    }
  })
}


export const useDeleteCourseClass = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, classId }) => {
      return apiClient.delete(`/courses/${courseId}/classes/${classId}`)
    },
    onSuccess: (_data, variables) => {
      void invalidateOrgQueries(queryClient, orgId, ['courses', 'classes'])
      void invalidatePreparationQueries(queryClient, orgId)
      queryClient.removeQueries({ queryKey: orgQueryKey('classes', orgId, variables.classId) })
      queryClient.removeQueries({ queryKey: orgQueryKey('class-subjects', orgId, variables.classId) })
      queryClient.removeQueries({ queryKey: orgQueryKey('available-subjects', orgId, variables.classId) })
    }
  })
}

// ==========================================
//  FASE 4: GESTÃO DE TURMAS (Esqueleto)
//  Implementação completa na Fase 5
// ==========================================

/**
 * Obter dashboard completo de uma turma.
 * 
 * Retorna: ClassFullDetailRead
 * - Dados da turma (nome, capacidade, grade_level, start_year, end_year)
 * - Curso associado (nome, sigla)
 * - Disciplinas com módulos e progresso (horas, percentagem, is_completed)
 * 
 * 4 Pilares:
 * - Scalability: Cache separada por classId
 * - Stability: enabled flag previne queries desnecessárias
 * - Optimization: Backend retorna tudo em 2 queries (vs N+1)
 */
export const useClassDetails = (classId) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('classes', orgId, classId),
    queryFn: async () => {
      return apiClient.get(`/classes/${classId}`)
    },
    enabled: Boolean(orgId) && Boolean(classId),
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
}

/**
 * Atualizar progresso de módulos de uma turma.
 * 
 * Uso:
 * const updateProgress = useUpdateClassProgress()
 * updateProgress.mutate({
 *   classId: 5,
 *   progress: [
 *     { module_id: 1, hours_completed: 25 },
 *     { module_id: 2, hours_completed: 50 }
 *   ]
 * })
 * 
 * 4 Pilares:
 * - Stability: Invalida cache da turma + lista para garantir consistência
 * - Security: Backend valida que módulos pertencem ao curso da turma
 */
export const useUpdateClassProgress = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, progress }) => {
      return apiClient.patch(`/classes/${classId}/progress`, { progress })
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(orgQueryKey('classes', orgId, variables.classId), data)
      void invalidateOrgQueries(queryClient, orgId, ['classes'])
    }
  })
}

// ==========================================
//  DISCIPLINAS DA TURMA (Class-Subject Link)
//  Gestão curso-cêntrica de professores
// ==========================================

/**
 * Lista disciplinas associadas à turma (para o grade_level atual).
 * Inclui professor atribuído a cada disciplina.
 * 
 * Usado na página ClassSubjects.jsx
 */
export const useClassSubjects = (classId) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('class-subjects', orgId, classId),
    queryFn: async () => {
      if (!classId) return null
      return apiClient.get(`/classes/${classId}/subjects`)
    },
    enabled: Boolean(orgId) && Boolean(classId),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
  })
}

/**
 * Lista disciplinas disponíveis para adicionar à turma.
 * (Disciplinas da org que ainda não estão associadas)
 */
export const useAvailableSubjects = (classId) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('available-subjects', orgId, classId),
    queryFn: async () => {
      if (!classId) return []
      return apiClient.get(`/classes/${classId}/available-subjects`)
    },
    enabled: Boolean(orgId) && Boolean(classId),
    staleTime: 1000 * 60 * 5,
  })
}

/**
 * Lista professores elegíveis para lecionar uma disciplina.
 * (Professores que têm competência na disciplina)
 */
export const useEligibleTeachers = (subjectId) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('eligible-teachers', orgId, subjectId),
    queryFn: async () => {
      if (!subjectId) return []
      return apiClient.get(`/classes/subjects/${subjectId}/eligible-teachers`)
    },
    enabled: Boolean(orgId) && Boolean(subjectId),
    staleTime: 1000 * 60 * 5,
  })
}

/**
 * Adiciona uma disciplina à turma.
 */
export const useAddClassSubject = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, subjectId }) => {
      return apiClient.post(`/classes/${classId}/subjects`, { subject_id: subjectId })
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(orgQueryKey('class-subjects', orgId, variables.classId), data)
      void invalidateOrgQueries(queryClient, orgId, ['available-subjects', 'classes', 'courses'])
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}

/**
 * Atualiza a atribuição de uma disciplina da turma.
 * Aceita apenas os campos definidos: `teacherId` e/ou `moduleIds`.
 */
export const useUpdateClassSubject = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, subjectId, teacherId, moduleIds }) => {
      const payload = {}
      if (teacherId !== undefined) payload.teacher_id = teacherId
      if (moduleIds !== undefined) payload.module_ids = moduleIds
      return apiClient.patch(`/classes/${classId}/subjects/${subjectId}`, payload)
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(orgQueryKey('class-subjects', orgId, variables.classId), data)
      // A joint teacher change propagates to every member link. Refresh the
      // other member class-subjects and the candidate facts (stale teacher).
      // The current class keeps the immediate response above.
      const jointClasses = data?.subjects
        ?.find((subject) => subject.subject_id === variables.subjectId)
        ?.joint_group?.classes ?? []
      const otherClassIds = jointClasses
        .map((cls) => cls.class_id)
        .filter((id) => id !== variables.classId)
      if (otherClassIds.length > 0) {
        invalidateJointMemberQueries(queryClient, orgId, otherClassIds)
      }
      void invalidateOrgQueries(queryClient, orgId, ['classes', 'teacher-progress'])
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}

/**
 * Remove uma disciplina da turma.
 */
export const useRemoveClassSubject = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, subjectId }) => {
      return apiClient.delete(`/classes/${classId}/subjects/${subjectId}`)
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(orgQueryKey('class-subjects', orgId, variables.classId), data)
      void invalidateOrgQueries(queryClient, orgId, ['available-subjects', 'classes', 'courses'])
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}

// ==========================================
//  AULAS CONJUNTAS (Junção)
// ==========================================

/**
 * Invalida a lista de disciplinas de todas as turmas membro, além das raízes de catálogo.
 */
const invalidateJointMemberQueries = (queryClient, orgId, classIds) => {
  const uniqueClassIds = [...new Set((classIds || []).filter(Boolean))]
  for (const classId of uniqueClassIds) {
    void queryClient.invalidateQueries({ queryKey: orgQueryKey('class-subjects', orgId, classId) })
  }
  void invalidateOrgQueries(queryClient, orgId, ['classes', 'readiness-bases', 'joint-candidates'])
  void invalidatePreparationQueries(queryClient, orgId)
}

/**
 * Turmas que podem entrar numa junção com a turma indicada.
 * Ao editar, `groupId` devolve também os membros atuais, incluindo a turma de origem.
 * `includeSource` pede as facts da própria turma (para bloquear módulos já começados).
 */
export const useJointCandidates = (subjectId, classId, groupId = null, includeSource = false) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const queryKey = includeSource
    ? orgQueryKey('joint-candidates', orgId, subjectId, classId, groupId, 'include_source')
    : orgQueryKey('joint-candidates', orgId, subjectId, classId, groupId)
  return useQuery({
    queryKey,
    queryFn: async () => {
      const params = { class_id: classId }
      if (groupId != null) params.group_id = groupId
      if (includeSource) params.include_source = true
      return apiClient.get(`/subjects/${subjectId}/joint-candidates`, { params })
    },
    enabled: Boolean(orgId) && Boolean(subjectId) && Boolean(classId),
    staleTime: 1000 * 60 * 5,
  })
}

/**
 * Cria uma junção.
 */
export const useCreateJointGroup = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ subjectId, classIds, moduleIds, teacherId }) => {
      return apiClient.post('/joint-lesson-groups', {
        subject_id: subjectId,
        class_ids: classIds,
        module_ids: moduleIds,
        teacher_id: teacherId,
      })
    },
    onSuccess: (_data, variables) => {
      invalidateJointMemberQueries(queryClient, orgId, variables.classIds)
    },
  })
}

/**
 * Substitui as turmas, módulos e professor de uma junção.
 * `previousClassIds` são as turmas que saem, para invalidar a cache delas.
 */
export const useUpdateJointGroup = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ groupId, classIds, moduleIds, teacherId }) => {
      return apiClient.put(`/joint-lesson-groups/${groupId}`, {
        class_ids: classIds,
        module_ids: moduleIds,
        teacher_id: teacherId,
      })
    },
    onSuccess: (_data, variables) => {
      invalidateJointMemberQueries(
        queryClient,
        orgId,
        [...(variables.classIds || []), ...(variables.previousClassIds || [])],
      )
    },
  })
}

/**
 * Desfaz uma junção. As turmas ficam com os mesmos módulos, todos separados.
 */
export const useDeleteJointGroup = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ groupId }) => {
      return apiClient.delete(`/joint-lesson-groups/${groupId}`)
    },
    onSuccess: (_data, variables) => {
      invalidateJointMemberQueries(queryClient, orgId, variables.classIds)
    },
  })
}

// ==========================================
//  SPRINT 2 — OCORRÊNCIAS & DÍVIDAS
// ==========================================

/**
 * Lista ocorrências com filtros opcionais (classId, dateFrom, dateTo).
 */
