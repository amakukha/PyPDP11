/*
 * Sum bytes in file mod 2^16
 * 
 * This is a backport of `sum` command from Unix V7 into Unix V6.
 * Unix V6 had the same implementation of `sum` as Version 5 and it was very
 * bad as a checksum.
 * 
 * Written in pre-K&R C.
 */

int ibuf[259];		/* struct buf */

main(argc,argv)
char **argv;
{
	int i, nsize;
	register int c, nbytes, sum;

	ibuf[0] = 0;	/* stdin */

	i = 1;
	do {
		if(i < argc) {
			if (fopen(argv[i], ibuf) < 0) {
				diag(argv[i]);
				diag(": cannot open\n");
				return;
			}
		}
		sum = 0;
		nbytes = 1024;
		nsize = 0;
		while ((c = getc(ibuf)) >= 0) {
			nbytes++;
			if (nbytes>1024) {
				nbytes =- 1024;
				nsize++;
			}
			if (sum&01) {
				if (sum>=0)
					sum = (sum>>1) | 0100000;
				else
					sum = sum>>1;
			} else {
				if (sum>=0)
					sum = sum>>1;
				else
					sum = ~( ((~sum)>>1) | 0100000 );
			}
			sum =+ c;
		}
		printf("%7s ",locv(0,sum));
		printf("%d",nsize);
		if(argc > 2)
			printf(" %s", argv[i]);
		printf("\n");
		close(ibuf);
	} while(++i < argc);
}

diag(s)
char *s;
{
	while(*s)
		write(2,s++,1);
}
