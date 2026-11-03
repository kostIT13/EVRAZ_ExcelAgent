import AnnexRunner from '@/components/pmi/AnnexRunner';

/**
 * Вкладка «Демо» — один экран прогона ПМИ: требования, шаги, вопросы в чат,
 * речь для комиссии и автопроверки стенда по каждому пункту приложения А.
 */
export default function DemoPage() {
  return (
    <div className="demo">
      <AnnexRunner />
    </div>
  );
}
