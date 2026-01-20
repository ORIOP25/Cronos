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
 */
export const useUpdateEntity = (entityKey) => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, ...updateData }) => {
      // PUT /teachers/1
      const { data } = await apiClient.put(`/${entityKey}/${id}`, updateData)
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