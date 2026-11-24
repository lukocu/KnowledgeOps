/** Pytanie konsultanta nad odpowiedzią (S1A/S1P/S1C). Tekst nie jest tłumaczony. */
export function QuestionBubble({ question }: { question: string }) {
  return (
    <div className="rounded-xl bg-surface px-4 py-3.5 text-[15px] leading-6 break-words whitespace-pre-wrap">
      {question}
    </div>
  );
}
