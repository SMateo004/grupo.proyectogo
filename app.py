package main

import (
	"context"
	"fmt"
	"math"
	"math/rand"
	"sort"
	"sync"
	"time"
)

type ProcesoSimulado struct {
	ID              int
	Nombre          string
	CargaBase       int // carga base multiplicativa
	MemoriaEstimada int
	JitterMax       time.Duration // variación aleatoria
}

type Instruccion struct {
	ID     int
	Accion string // "iniciar", "detener"
}

type Tarea struct {
	ProcesoID int
	Ronda     int
	Carga     int // carga específica de la tarea (se multiplica por CargaBase)
}

type Resultado struct {
	ProcesoID int
	Nombre    string
	Ronda     int
	Memoria   int
	Tiempo    time.Duration
	OK        bool
	Err       string
}

type Confirmacion struct {
	ProcesoID  int
	Ronda      int
	Accion     string
	Completado bool
}

// --- Utilidades de métricas ---

type Stats struct {
	Count   int
	AvgMs   float64
	P50Ms   float64
	P95Ms   float64
	MaxMs   float64
	MinMs   float64
	SumMs   float64
	Samples []float64
}

func (s *Stats) add(d time.Duration) {
	ms := float64(d.Milliseconds())
	s.Samples = append(s.Samples, ms)
	s.SumMs += ms
	s.Count++
	if s.Count == 1 {
		s.MinMs, s.MaxMs = ms, ms
	} else {
		if ms < s.MinMs {
			s.MinMs = ms
		}
		if ms > s.MaxMs {
			s.MaxMs = ms
		}
	}
}

func (s *Stats) finalize() {
	if s.Count == 0 {
		return
	}
	s.AvgMs = s.SumMs / float64(s.Count)
	sort.Float64s(s.Samples)
	s.P50Ms = percentile(s.Samples, 50)
	s.P95Ms = percentile(s.Samples, 95)
}

func percentile(sorted []float64, p float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	if p <= 0 {
		return sorted[0]
	}
	if p >= 100 {
		return sorted[len(sorted)-1]
	}
	pos := (p / 100.0) * float64(len(sorted)-1)
	i := int(math.Floor(pos))
	f := pos - float64(i)
	if i+1 < len(sorted) {
		return sorted[i]*(1-f) + sorted[i+1]*f
	}
	return sorted[i]
}

// --- Proceso ---

func simularProceso(
	p ProcesoSimulado,
	ctx context.Context,
	instrCh <-chan Instruccion,
	tareasCh <-chan Tarea,
	resultadosCh chan<- Resultado,
	confirmCh chan<- Confirmacion,
	wg *sync.WaitGroup,
) {
	defer wg.Done()

	for {
		select {
		case <-ctx.Done():
			fmt.Printf("[Proceso %s] cancelado por contexto\n", p.Nombre)
			return

		case instr, ok := <-instrCh:
			if !ok {
				return
			}
			switch instr.Accion {
			case "detener":
				fmt.Printf("Proceso %s (%d) detenido.\n", p.Nombre, p.ID)
				return
			}

		case tarea, ok := <-tareasCh:
			if !ok {
				return
			}
			if tarea.ProcesoID != p.ID {
				// Ignorar tareas no destinadas a este proceso (defensivo)
				continue
			}

			// Simular trabajo
			start := time.Now()
			// tiempo = (cargaBase * cargaTarea * 100ms) + jitter
			base := time.Duration(p.CargaBase*tarea.Carga) * 100 * time.Millisecond
			jitter := time.Duration(rand.Int63n(int64(p.JitterMax)))
			time.Sleep(base + jitter)
			elapsed := time.Since(start)

			// Emitir resultado
			resultadosCh <- Resultado{
				ProcesoID: p.ID,
				Nombre:    p.Nombre,
				Ronda:     tarea.Ronda,
				Memoria:   p.MemoriaEstimada,
				Tiempo:    elapsed,
				OK:        true,
			}

			// Confirmar
			confirmCh <- Confirmacion{
				ProcesoID:  p.ID,
				Ronda:      tarea.Ronda,
				Accion:     "tarea",
				Completado: true,
			}
		}
	}
}

// --- Coordinador ---

func coordinador(
	procesos []ProcesoSimulado,
	rondas int,
	timeoutRonda time.Duration, // si es 0, sin timeout
	instr map[int]chan Instruccion,
	tareas map[int]chan Tarea,
	resultados <-chan Resultado,
	confirm <-chan Confirmacion,
) {

	// Enviar rondas de trabajo
	for r := 1; r <= rondas; r++ {
		fmt.Printf("\n=== Ronda %d ===\n", r)

		// Contexto de timeout por ronda (opcional)
		var (
			ctx  context.Context
			stop context.CancelFunc
		)
		if timeoutRonda > 0 {
			ctx, stop = context.WithTimeout(context.Background(), timeoutRonda)
		} else {
			ctx, stop = context.WithCancel(context.Background())
		}

		// Despachar 1 tarea por proceso en esta ronda
		for _, p := range procesos {
			carga := rand.Intn(5) + 1 // 1..5 (puedes parametrizarlo)
			tareas[p.ID] <- Tarea{ProcesoID: p.ID, Ronda: r, Carga: carga}
		}

		// Esperar resultados de la ronda
		pendientes := len(procesos)
		for pendientes > 0 {
			select {
			case <-ctx.Done():
				fmt.Printf("[Coordinador] Timeout en ronda %d, continúo con lo recibido.\n", r)
				pendientes = 0 // salimos de la espera de la ronda
			case res := <-resultados:
				if res.Ronda == r {
					fmt.Printf("Resultado: P%d|%s | Ronda %d | %v | Mem: %dMB\n",
						res.ProcesoID, res.Nombre, res.Ronda, res.Tiempo, res.Memoria)
					pendientes--
				} else {
					// Resultado tardío de otra ronda; lo imprimimos igual
					fmt.Printf("Resultado tardío: P%d|%s | Ronda %d | %v\n",
						res.ProcesoID, res.Nombre, res.Ronda, res.Tiempo)
				}
			case c := <-confirm:
				_ = c // aquí podríamos validar por ID/ronda si queremos
			}
		}
		stop()
	}

	// Orden de parada
	for _, p := range procesos {
		instr[p.ID] <- Instruccion{ID: p.ID, Accion: "detener"}
	}

	// Cerrar canales de instrucciones/tareas para que terminen los procesos
	for _, ch := range instr {
		close(ch)
	}
	for _, ch := range tareas {
		close(ch)
	}
}

// --- Agregador de métricas ---

func recolectorMetricas(
	wg *sync.WaitGroup,
	resultados <-chan Resultado,
	done chan<- map[int]*Stats,
) {
	defer wg.Done()

	porProceso := map[int]*Stats{}
	global := &Stats{}

	for res := range resultados {
		if res.OK {
			if porProceso[res.ProcesoID] == nil {
				porProceso[res.ProcesoID] = &Stats{}
			}
			porProceso[res.ProcesoID].add(res.Tiempo)
			global.add(res.Tiempo)
		}
	}

	// Finalizar stats
	for _, st := range porProceso {
		st.finalize()
	}
	global.finalize()

	// Empaquetar resultado (id 0 = global)
	porProceso[0] = global
	done <- porProceso
	close(done)
}

func main() {
	rand.Seed(time.Now().UnixNano())

	// --- Configuración ---
	rondas := 7

	timeoutRonda := 2 * time.Second // pon 0 para sin timeout

	procesos := []ProcesoSimulado{
		{ID: 1, Nombre: "Proceso_A", CargaBase: rand.Intn(3) + 1, MemoriaEstimada: rand.Intn(100) + 50, JitterMax: 200 * time.Millisecond},
		{ID: 2, Nombre: "Proceso_B", CargaBase: rand.Intn(3) + 1, MemoriaEstimada: rand.Intn(100) + 50, JitterMax: 200 * time.Millisecond},
		{ID: 3, Nombre: "Proceso_C", CargaBase: rand.Intn(3) + 1, MemoriaEstimada: rand.Intn(100) + 50, JitterMax: 300 * time.Millisecond},
	}

	// --- Canales ---
	instr := make(map[int]chan Instruccion, len(procesos))
	tareas := make(map[int]chan Tarea, len(procesos))
	resultados := make(chan Resultado, 128)
	confirm := make(chan Confirmacion, 128)

	// --- Lanzar procesos ---
	var wgProc sync.WaitGroup
	ctxGlobal, cancel := context.WithCancel(context.Background())
	for _, p := range procesos {
		instr[p.ID] = make(chan Instruccion, 2)
		tareas[p.ID] = make(chan Tarea, 8)
		wgProc.Add(1)
		go simularProceso(p, ctxGlobal, instr[p.ID], tareas[p.ID], resultados, confirm, &wgProc)
	}

	// --- Recolector de métricas ---
	var wgRec sync.WaitGroup
	doneStats := make(chan map[int]*Stats, 1)
	wgRec.Add(1)
	go recolectorMetricas(&wgRec, resultados, doneStats)

	// --- Coordinador ---
	coordinador(procesos, rondas, timeoutRonda, instr, tareas, resultados, confirm)

	// Cerrar salidas de procesos y esperar
	wgProc.Wait()
	cancel() // por si acaso
	close(resultados)
	close(confirm)

	// Esperar agregación de métricas
	wgRec.Wait()
	statsPorProceso := <-doneStats

	// --- Reporte ---
	fmt.Println("\n====== MÉTRICAS ======")
	for _, p := range procesos {
		if st := statsPorProceso[p.ID]; st != nil && st.Count > 0 {
			fmt.Printf("[%s] n=%d avg=%.1fms p50=%.1fms p95=%.1fms min=%.1fms max=%.1fms\n",
				p.Nombre, st.Count, st.AvgMs, st.P50Ms, st.P95Ms, st.MinMs, st.MaxMs)
		} else {
			fmt.Printf("[%s] sin datos\n", p.Nombre)
		}
	}
	if g := statsPorProceso[0]; g != nil && g.Count > 0 {
		fmt.Printf("[GLOBAL] n=%d avg=%.1fms p50=%.1fms p95=%.1fms min=%.1fms max=%.1fms\n",
			g.Count, g.AvgMs, g.P50Ms, g.P95Ms, g.MinMs, g.MaxMs)
	}
	fmt.Println("Simulación completada.")
}
