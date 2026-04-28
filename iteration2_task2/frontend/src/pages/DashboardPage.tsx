import { SummaryCards } from "../components/SummaryCards";
import { TaskTable } from "../components/TaskTable";
import type { EvaluationTask, TaskStatus } from "../types/task";

interface DashboardPageProps {
  tasks: EvaluationTask[];
  selectedTaskId?: string;
  selectedCompareIds: string[];
  onSelectTask: (taskId: string) => void;
  onToggleCompare: (taskId: string) => void;
  onRunTask: (taskId: string) => void;
  onChangeStatus: (taskId: string, status: TaskStatus) => void;
  onDeleteTask: (taskId: string) => void;
}

export function DashboardPage(props: DashboardPageProps) {
  const running = props.tasks.filter((task) => task.status === "running").length;
  const completed = props.tasks.filter((task) => task.status === "completed").length;
  const customMetrics = props.tasks.reduce(
    (sum, task) => sum + task.config.custom_metrics.length,
    0
  );

  return (
    <div className="page-grid">
      <SummaryCards
        total={props.tasks.length}
        running={running}
        completed={completed}
        customMetrics={customMetrics}
      />
      <TaskTable
        tasks={props.tasks}
        selectedTaskId={props.selectedTaskId}
        selectedCompareIds={props.selectedCompareIds}
        onSelectTask={props.onSelectTask}
        onToggleCompare={props.onToggleCompare}
        onRunTask={props.onRunTask}
        onChangeStatus={props.onChangeStatus}
        onDeleteTask={props.onDeleteTask}
      />
    </div>
  );
}
