import Link from "next/link";

export default function Home() {
  return (
    <main className="home-redirect">
      <div className="home-redirect__card">
        <h1>Quantum Agent</h1>
        <p>可信、多模态、Learning-Native 的量子物理教学智能体。</p>
        <Link href="/agent" className="home-redirect__cta">
          进入学情工作台 →
        </Link>
      </div>
    </main>
  );
}
