import { ResultsLoader } from "../../../components/game/results-loader";

export default function ResultsPage({ params }: { params: { id: string } }) {
  return <ResultsLoader id={params.id} />;
}
