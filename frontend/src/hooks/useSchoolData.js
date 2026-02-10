import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'

/**
 * CONFIGURAÇÃO DE CACHE (A "Magia" da Performance)
 * * STATIC_OPTS: Para dados que mudam raramente (Metadados).
 * - Cache de 30 minutos.
 * - Não recarrega quando mudas de janela.
 * * DYNAMIC_OPTS: Para dados operacionais (Horários, Substituições).
 * - Cache de 5 minutos (ou menos, se preferires).
 * - Mantemos refetchOnWindowFocus para garantir que o utilizador vê dados frescos se voltar à tab.
 */
const STATIC_OPTS = {
  staleTime: 1000 * 60 * 30, // 30 minutos sem pedir ao servidor
  refetchOnWindowFocus: false,
  refetchOnMount: false, // Se o componente desmontar e montar, usa a cache
  retry: 1
}

const DYNAMIC_OPTS = {
  staleTime: 1000 * 60 * 5, // 5 minutos de "frescura"
  refetchOnWindowFocus: true,
  retry: 2
}

// --- HOOKS DE LEITURA (Read) ---

export const useTeachers = () => useQuery({
  queryKey: ['teachers'],
  queryFn: async () => {
    // Nota: Futuramente podes migrar de '/import/teachers' para '/teachers/'
    const { data } = await apiClient.get('/import/teachers')
    return data
  },
  ...STATIC_OPTS
})

export const useRooms = () => useQuery({
  queryKey: ['rooms'],
  queryFn: async () => {
    const { data } = await apiClient.get('/import/rooms')
    return data
  },
  ...STATIC_OPTS
})

export const useSubjects = () => useQuery({
  queryKey: ['subjects'],
  queryFn: async () => {
    const { data } = await apiClient.get('/import/subjects')
    return data
  },
  ...STATIC_OPTS
})

export const useClasses = () => useQuery({
  queryKey: ['classes'],
  queryFn: async () => {
    const { data } = await apiClient.get('/classes/')
    return data
  },
  ...STATIC_OPTS
})

export const useLessons = () => useQuery({
  queryKey: ['lessons'],
  queryFn: async () => {
    const { data } = await apiClient.get('/import/lessons')
    return data
  },
  ...STATIC_OPTS
})

export const useTimeslots = () => useQuery({
  queryKey: ['timeslots'],
  queryFn: async () => {
    const { data } = await apiClient.get('/timeslots/')
    return data
  },
  ...STATIC_OPTS
})

// --- CURSOS ---
export const useCourses = () => useQuery({
  queryKey: ['courses'],
  queryFn: async () => {
    const { data } = await apiClient.get('/courses/')
    return data
  },
  ...STATIC_OPTS
})

// --- MÓDULOS ---
export const useModules = () => useQuery({
  queryKey: ['modules'],
  queryFn: async () => {
    const { data } = await apiClient.get('/modules/')
    return data
  },
  ...STATIC_OPTS
})

// --- CURRÍCULO DA TURMA (Dados Relacionados) ---
/**
 * Hook para carregar o currículo (disciplinas) de uma turma.
 * 
 * Implementa o padrão de "Dados Relacionados":
 * - enabled=!!classId: Só faz fetch se classId existir
 * - queryKey inclui classId: Cache separada por turma
 * - STATIC_OPTS: Currículo muda raramente
 * 
 * Uso:
 * const { data: curriculum, isLoading } = useClassCurriculum(5)
 */
export const useClassCurriculum = (classId) => useQuery({
  queryKey: ['class-curriculum', classId],
  queryFn: async () => {
    // Proteção: Se classId é falsy, retorna array vazio
    if (!classId) return []
    const { data } = await apiClient.get(`/classes/${classId}/curriculum`)
    return data
  },
  // OTIMIZAÇÃO: Só faz fetch se classId existir
  enabled: !!classId,
  ...STATIC_OPTS
})

// --- HOOKS OPERACIONAIS (Dinâmicos) ---

export const useSchedule = () => useQuery({
  queryKey: ['schedule'],
  queryFn: async () => {
    const { data } = await apiClient.get('/schedule/latest')
    return data
  },
  ...DYNAMIC_OPTS
})

export const useSubstitutions = () => useQuery({
  queryKey: ['substitutions'],
  queryFn: async () => {
    const { data } = await apiClient.get('/substitutions/')
    return data
  },
  staleTime: 1000 * 60, // 1 minuto
  refetchOnWindowFocus: true
})

// ==========================================
//  HOOKS DE MUTAÇÃO GENÉRICOS (CRUD Factory)
//  Estes hooks gerem a escrita e a atualização automática da cache.
// ==========================================

/**
 * Cria uma nova entidade.
 * @param {string} entityKey - O nome da entidade (ex: 'teachers'). Define o URL (/teachers/) e a Cache Key.
 */
export const useCreateEntity = (entityKey) => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (newItem) => {
      // POST /teachers/
      const { data } = await apiClient.post(`/${entityKey}/`, newItem)
      return data
    },
    onSuccess: () => {
      // Invalida a cache ['teachers'] para forçar recarregamento na tabela
      queryClient.invalidateQueries({ queryKey: [entityKey] })
    }
  })
}

/**
 * Atualiza uma entidade existente.
 * Uso: mutate({ id: 1, name: "Novo Nome" })
 * 
 * PATCH: Atualização parcial (apenas campos enviados)
 */
export const useUpdateEntity = (entityKey) => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, ...updateData }) => {
      // PATCH /courses/1 (atualização parcial - apenas os campos enviados)
      const { data } = await apiClient.patch(`/${entityKey}/${id}`, updateData)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [entityKey] })
    }
  })
}

/**
 * Apaga uma entidade.
 * Uso: mutate(1)
 */
export const useDeleteEntity = (entityKey) => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id) => {
      // DELETE /teachers/1
      await apiClient.delete(`/${entityKey}/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [entityKey] })
    }
  })
}

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
export const useCourseDetails = (courseId) => useQuery({
  queryKey: ['courses', courseId],
  queryFn: async () => {
    const { data } = await apiClient.get(`/courses/${courseId}`)
    return data
  },
  enabled: !!courseId, // Optimization: Só dispara se houver ID
  staleTime: 1000 * 60 * 5, // 5 minutos (dados semi-estáticos)
  refetchOnWindowFocus: false, // Stability: Não recarrega ao voltar à tab
})

/**
 * Criar novo curso com turmas automáticas.
 * 
 * 4º Pilares:
 * - Security: Backend valida abbreviation uniqueness
 * - Stability: onSuccess invalida caches para garantir consistência
 * 
 * Uso:
 * const createCourse = useCreateCourse()
 * createCourse.mutate({
 *   name: "Técnico em Informática",
 *   abbreviation: "TI",
 *   subject_ids: [1, 2],
 *   classes_config: [
 *     { grade_level: 10, size: 25, start_year: 2025, end_year: 2028 }
 *   ]
 * })
 */
export const useCreateCourse = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (newCourse) => {
      const { data } = await apiClient.post('/courses/', newCourse)
      return data
    },
    onSuccess: () => {
      // Invalidar caches de listagem para forçar recarregamento
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    }
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
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ courseId, data }) => {
      const { data: response } = await apiClient.patch(`/courses/${courseId}`, data)
      return response
    },
    onSuccess: (data, variables) => {
      // Invalidar listagem
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      // Invalidar detalhe específico para garantir sincronização
      queryClient.invalidateQueries({ queryKey: ['courses', variables.courseId] })
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
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (courseId) => {
      await apiClient.delete(`/courses/${courseId}`)
    },
    onSuccess: () => {
      // Invalida caches de cursos (listagem e potenciais detalhes)
      queryClient.invalidateQueries({ queryKey: ['courses'] })
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
export const useClassDetails = (classId) => useQuery({
  queryKey: ['classes', classId],
  queryFn: async () => {
    const { data } = await apiClient.get(`/classes/${classId}`)
    return data
  },
  enabled: !!classId,
  staleTime: 1000 * 60 * 5,
  refetchOnWindowFocus: false,
})

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
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ classId, progress }) => {
      const { data } = await apiClient.patch(`/classes/${classId}/progress`, { progress })
      return data
    },
    onSuccess: (data, variables) => {
      // Atualizar cache do detalhe com dados frescos do servidor
      queryClient.setQueryData(['classes', variables.classId], data)
      // Invalidar lista de turmas (progresso pode afetar UI da lista)
      queryClient.invalidateQueries({ queryKey: ['classes'] })
    }
  })
}