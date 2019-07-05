/* reverse "od -h" operation on Unix V6 */
/* written in pre-K&R C */
/* derived from wc.c and cvopt.c */

int ibuf[259];
int obuf[259];

main(argc,argv)
char **argv;
{
	int token, bytecnt;
	register char *p1, *p2;		/* input buffer pointers */
	register int c;			/* char or read count */
	char sp, b1, b2, lastc, lastb2, nfirst;

	obuf[0] = 1;			/* standard output by default */
	if (argc>2) {
					/* create output file */
		if ((obuf[0] = creat(argv[2], 0666)) < 0) {
			diag(argv[2]);
			diag(": failed to create\n");
			return;
		}
	}
	if (argc>1 && fopen(argv[1], ibuf)>=0) {
		p1 = 0;
		p2 = 0;
		sp = 0;
		token = 0;
		bytecnt = 0;
		nfirst = 0;
		for(;;) {
			/* reading from file */
			if (p1 >= p2) {
				p1 = &ibuf[1];
				c = read(ibuf[0], p1, 512);
				if (c <= 0)
					break;
				p2 = p1+c;
			}
			/* decoding loop */
			c = 0;
			c =| *p1++;
			if (c==' ' || c=='\n') {
				b1 = token;
				b2 = token >> 8;
				if (lastc!=' ' && lastc!='\n') {
					/* end of token */
					if (sp>0) {
						if (nfirst) putc(lastb2, obuf);
						putc(b1, obuf);
						lastb2 = b2;
						nfirst = 1;
					} else {
						/* first token in the line */
						bytecnt = token;
					}
				}
				if (c==' ') sp++;
				else {
					/* new line */
					sp = 0;
					fflush(obuf);
				}
				token = 0;
			} else {
				/* actual hex and octal conversion */
				token =* sp>0 ? 16 : 8;
				token =+ c<='9' ? c-'0' : c-'W';
			}
			lastc = c;
		}
		if (!(bytecnt & 1)) {
			putc(lastb2, obuf);
			fflush(obuf);
		}
		close(ibuf[0]);
		close(obuf[0]);
	} else if (argc>1) {
		diag(argv[1]);
		diag(": cannot open\n");
	} else {
		diag("error: filename missing\n");
	}
}

diag(s)
char *s;
{
	while(*s)
		write(2,s++,1);
}
