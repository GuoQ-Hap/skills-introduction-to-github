import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { notification } from 'antd';
import { useNavigate } from 'react-router-dom';
import { listingApi } from '../api';

const POLL_INTERVAL = 3000;
const STORAGE_KEY = 'lsta_bg_tasks';

type TaskAction = 'optimize' | 'analyze' | 'discover_competitors' | 'review_analysis' | 'fetch_product' | 'fetch_reviews';

/** 多候选优化的阶段性进度（运行中阶段由后端 on_progress 推送） */
export interface OptimizePartial {
  phase?: 'init' | 'generate' | 'evaluate' | 'done';
  total: number;
  generated: number;
  evaluated: number;
  variants: any[];
}

export interface TaskInfo {
  taskId: string;
  action: TaskAction;
  asin: string;
  marketplace: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: any;
  /** 运行中的阶段性产出（如多候选优化的已完成候选） */
  partial?: OptimizePartial;
  error?: string;
  elapsedMs?: number;
  submittedAt: number;
}

interface TaskContextValue {
  tasks: Map<string, TaskInfo>;
  submitTask: (
    action: TaskAction,
    params: Record<string, unknown>,
    meta: { asin: string; marketplace: string },
  ) => Promise<string>;
  getTaskResult: (taskId: string) => TaskInfo | undefined;
  getActiveTaskForAsin: (asin: string, action?: string) => TaskInfo | undefined;
  clearTask: (taskId: string) => void;
  clearAllTasks: () => void;
}

const TaskContext = createContext<TaskContextValue | null>(null);

function loadPersistedTasks(): Map<string, TaskInfo> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return new Map();
    const arr: TaskInfo[] = JSON.parse(raw);
    return new Map(arr.map((t) => [t.taskId, t]));
  } catch {
    return new Map();
  }
}

function persistTasks(tasks: Map<string, TaskInfo>) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...tasks.values()]));
  } catch { /* quota */ }
}

export function TaskProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Map<string, TaskInfo>>(loadPersistedTasks);
  const tasksRef = useRef(tasks);
  tasksRef.current = tasks;
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const navigate = useNavigate();

  const updateTask = useCallback((taskId: string, patch: Partial<TaskInfo>) => {
    setTasks((prev) => {
      const next = new Map(prev);
      const existing = next.get(taskId);
      if (existing) {
        next.set(taskId, { ...existing, ...patch });
      }
      persistTasks(next);
      return next;
    });
  }, []);

  const pollTasks = useCallback(async () => {
    const current = tasksRef.current;
    const pendingIds = [...current.entries()]
      .filter(([, t]) => t.status === 'pending' || t.status === 'running')
      .map(([id]) => id);

    if (pendingIds.length === 0) return;

    for (const taskId of pendingIds) {
      try {
        const { data } = await listingApi.getTaskStatus(taskId);
        const info = current.get(taskId);
        if (!info) continue;

        if (data.status === 'completed' && info.status !== 'completed') {
          updateTask(taskId, {
            status: 'completed',
            result: data.result as TaskInfo['result'],
            elapsedMs: data.elapsed_ms,
          });
          const ACTION_LABELS: Record<string, string> = {
            optimize: '优化', analyze: '诊断',
            discover_competitors: '竞品发现', review_analysis: '评论分析',
            fetch_product: '产品获取', fetch_reviews: '评论抓取',
          };
          const ACTION_ROUTES: Record<string, string> = {
            optimize: '/listing?tab=optimize', analyze: '/listing?tab=analyze',
            discover_competitors: '/competitors', review_analysis: '/reviews',
            fetch_product: '/listing', fetch_reviews: '/reviews',
          };
          const actionLabel = ACTION_LABELS[info.action] || info.action;
          notification.success({
            message: `${info.asin} ${actionLabel}完成`,
            description: `耗时 ${((data.elapsed_ms || 0) / 1000).toFixed(1)} 秒`,
            btn: undefined,
            key: taskId,
            duration: 8,
            onClick: () => {
              navigate(ACTION_ROUTES[info.action] || '/');
              notification.destroy(taskId);
            },
          });
        } else if (data.status === 'failed' && info.status !== 'failed') {
          updateTask(taskId, {
            status: 'failed',
            error: data.error,
            elapsedMs: data.elapsed_ms,
          });
          const ACTION_LABELS2: Record<string, string> = {
            optimize: '优化', analyze: '诊断',
            discover_competitors: '竞品发现', review_analysis: '评论分析',
            fetch_product: '产品获取', fetch_reviews: '评论抓取',
          };
          const actionLabel = ACTION_LABELS2[info.action] || info.action;
          notification.error({
            message: `${info.asin} ${actionLabel}失败`,
            description: data.error || '未知错误',
            key: taskId,
            duration: 10,
          });
        } else if (data.status !== info.status) {
          updateTask(taskId, {
            status: data.status as TaskInfo['status'],
            elapsedMs: data.elapsed_ms,
            partial: (data as { partial_result?: OptimizePartial }).partial_result ?? info.partial,
          });
        } else if ((data as { partial_result?: OptimizePartial }).partial_result) {
          // 状态未变化但有新的阶段性进度，仅更新 partial（避免 React 无意义重渲染）
          const newPartial = (data as { partial_result?: OptimizePartial }).partial_result!;
          const oldPartial = info.partial;
          if (
            !oldPartial ||
            oldPartial.generated !== newPartial.generated ||
            oldPartial.evaluated !== newPartial.evaluated ||
            (oldPartial.variants?.length || 0) !== (newPartial.variants?.length || 0)
          ) {
            updateTask(taskId, {
              partial: newPartial,
              elapsedMs: data.elapsed_ms,
            });
          }
        }
      } catch (e: unknown) {
        // 404：后端任务已不存在（服务重启/任务过期），终结这个僵尸任务以解除 UI 卡死
        const status = (e as { status?: number })?.status;
        if (status === 404) {
          const info = current.get(taskId);
          if (info && info.status !== 'failed' && info.status !== 'completed') {
            updateTask(taskId, {
              status: 'failed',
              error: '任务已丢失（服务可能已重启），请重新提交',
            });
            const ACTION_LABELS: Record<string, string> = {
              optimize: '优化', analyze: '诊断',
              discover_competitors: '竞品发现', review_analysis: '评论分析',
              fetch_product: '产品获取', fetch_reviews: '评论抓取',
            };
            const actionLabel = ACTION_LABELS[info.action] || info.action;
            notification.warning({
              message: `${info.asin} ${actionLabel}任务已丢失`,
              description: '后端服务可能已重启，原任务状态无法恢复，请重新提交。',
              key: taskId,
              duration: 8,
            });
          }
        }
        // 其他网络错误不中断轮询，下个周期再试
      }
    }
  }, [updateTask, navigate]);

  useEffect(() => {
    timerRef.current = setInterval(pollTasks, POLL_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [pollTasks]);

  const submitTask = useCallback(
    async (
      action: TaskAction,
      params: Record<string, unknown>,
      meta: { asin: string; marketplace: string },
    ): Promise<string> => {
      const body: Record<string, unknown> = { action };
      if (action === 'optimize') body.optimize_params = params;
      else if (action === 'analyze') body.analyze_params = params;
      else if (action === 'discover_competitors') body.competitor_params = params;
      else if (action === 'review_analysis') body.review_analysis_params = params;
      else if (action === 'fetch_product' || action === 'fetch_reviews') body.fetch_params = params;

      const { data } = await listingApi.submitTask(
        body as Parameters<typeof listingApi.submitTask>[0],
      );
      const taskId = data.task_id;

      const info: TaskInfo = {
        taskId,
        action,
        asin: meta.asin,
        marketplace: meta.marketplace,
        status: 'pending',
        submittedAt: Date.now(),
      };

      setTasks((prev) => {
        const next = new Map(prev);
        next.set(taskId, info);
        persistTasks(next);
        return next;
      });

      return taskId;
    },
    [],
  );

  const getTaskResult = useCallback(
    (taskId: string) => tasksRef.current.get(taskId),
    [],
  );

  const getActiveTaskForAsin = useCallback(
    (asin: string, action?: string) => {
      for (const t of tasksRef.current.values()) {
        if (
          t.asin === asin &&
          (!action || t.action === action) &&
          (t.status === 'pending' || t.status === 'running')
        ) {
          return t;
        }
      }
      return undefined;
    },
    [],
  );

  const clearTask = useCallback((taskId: string) => {
    setTasks((prev) => {
      const next = new Map(prev);
      next.delete(taskId);
      persistTasks(next);
      return next;
    });
    listingApi.deleteTask(taskId).catch(() => {});
  }, []);

  const clearAllTasks = useCallback(() => {
    setTasks((prev) => {
      for (const [id, t] of prev) {
        if (t.status === 'completed' || t.status === 'failed') {
          listingApi.deleteTask(id).catch(() => {});
        }
      }
      const next = new Map<string, TaskInfo>();
      persistTasks(next);
      return next;
    });
  }, []);

  return (
    <TaskContext.Provider
      value={{ tasks, submitTask, getTaskResult, getActiveTaskForAsin, clearTask, clearAllTasks }}
    >
      {children}
    </TaskContext.Provider>
  );
}

export function useTaskManager() {
  const ctx = useContext(TaskContext);
  if (!ctx) throw new Error('useTaskManager must be used within TaskProvider');
  return ctx;
}
