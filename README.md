본 프로젝트는 웹 기반 Mini DAW(Digital Audio Workstation)로,
사용자가 채팅 형태의 자연어 명령을 입력하면 시스템이 이를 해석하여
음악 편집(노트 배치, 드럼 패턴, 이동, 삭제 등) 및
오디오 샘플 생성을 자동으로 수행하는 것을 목표로 한다.

fastAPI를 활용해 작성되었다.
실행 방식은 다음과 같다.
cd mini_daw/
uvicorn app.main:app --reload

실행 전 
pip install -r requirments.txt 
... 를 실행해 의존성 라이브러리를 설치한다. 보다 빠른 실행을 위해서는 torch는 가능한 cuda버전을 미리 설치한다.
