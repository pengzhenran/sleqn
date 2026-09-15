Program sleqn
!==============================================================================
!  海平面指纹（Sea Level Fingerprints, SLF）计算程序  —— 求解海平面方程
!
!  功能：
!    由给定的全球表面（陆地水/冰）质量变化网格，计算考虑弹性负荷响应
!    （可选含极移反馈）之后的海平面指纹（即相对海平面变化的空间分布）。
!
!  输入文件：
!    land.fcn.1_deg  海陆掩膜，每行 "经度 纬度 value"（value=1 陆地，0 海洋）
!                    按纬度带顺序排列，共 nth*nphi 行
!    love_numbers    负荷勒让德数，前 2 行为表头，其后每行 "l  h_l  k_l  ..."
!                    （l = 0 ~ 180）
!    Filelist.txt    控制文件，每行两个文件名：输入数据文件、输出结果文件
!    输入数据文件    每行 "经度 纬度 水当量高度(m)"
!
!  输出文件：
!    每个输入文件对应一个输出文件，每行 "经度 纬度 海平面变化(cm)"
!    （经度外层循环、纬度内层循环，与输入网格顺序一致）
!
!  参考：
!    Sun J. W., Wang L. S., Peng Z. R., Fu Z. Y., Chen C (2022).
!    The sea level fingerprints of global terrestrial water storage
!    changes detected by GRACE and GRACE-FO data.
!    Pure and Applied Geophysics, 179(9).
!
!  编译：
!    gfortran -O2 -o sleqn.exe sleqn.f90        （Windows）
!    gfortran -O2 -o sleqn sleqn.f90            （Linux/macOS）
!
!  使用：
!    把下面标注 ★ 的三处文件名改成自己计算机上的本地文件，编译成 exe 运行即可。
!    程序按 Filelist.txt 逐行处理：读入一个质量变化网格 → 计算 → 输出一个结果文件。
!    niter 为迭代次数；niter=0 表示把水均匀铺在一层海面上（不做自吸引/负荷迭代）。
!==============================================================================

!//变量定义
      Parameter (lmost=180)
      Parameter (lsyn=lmost)
      Parameter (llove=lmost)
      Parameter (nth=180, nphi=360, niter=2)
      Implicit Real*8 (A-H, O-Z)

!     勒让德函数一套变量
      Dimension hclm(0:lmost, 0:lmost), hslm(0:lmost, 0:lmost), &
                clm1(0:lmost, 0:lmost), slm1(0:lmost, 0:lmost), &
                synthc(0:lsyn, 0:lsyn), synths(0:lsyn, 0:lsyn), &
                plmart(0:lmost, 0:lmost), pdum(0:lmost), &
                plm(0:lmost, 0:lmost, nth)
!     love数一套变量
      Dimension ccos(0:lmost, nphi), ssin(0:lmost, nphi), &
                coefp(0:llove), coefh(0:llove), rk(0:llove), h(0:llove)
!     网格与结果变量
      Dimension ofcn(nphi, nth), rlon(nphi), rlat(nth), total(nphi, nth)

      Character*120 namein, nameout
 11   Format (1X)
 22   Format (F5.1, 1X, F5.1, 1X, E12.4)

      pi = 3.14159265
      dtr = pi/180.0
      rho0 = 1.0
      rhoave = 5.517
      arad = 6.371E8
      rkf = 0.00328475/0.00348118
      rk2b = 0.298
      h2b = 0.604
      lmax = lmost
!变量定义//

!//赋值海面指代及love数
      Open (80, File='land.fcn.1_deg')          ! ★1 陆地区域mask文件
!     注意：ivalue 因隐式类型规则为整型（字母 i 不在 A-H/O-Z 之内），
!     因此掩膜文件第 3 列应写成整数 0/1，不能写成 0.0/1.0。
      Do j = 1, nth
        Do i = 1, nphi
          Read(80, *) rlon(i), rlat(j), ivalue
          ofcn(i, j) = float(1-ivalue)
!         write (99,*) rlon(i), rlat(j), ofcn(i, j)
        EndDo
      EndDo

      Open(90, File='love_numbers', Status='unknown')   ! ★2 love数文件名
      Read(90, 11)
      Read(90, 11)
      Do l = 0, llove
        Read(90, *) ldum, h(l), rk(l), rll
        coefh(l) = (1.+rk(l)-h(l))*3.*rho0/rhoave/float(2*l+1)
        coefp(l) = (1.+rk(l)-h(l))/(rk(l)+1)
      EndDo
!赋值海面指代及love数//

!//读入输入文件
      Open (100, File='Filelist.txt')           ! ★3 控制文件
!     需要两列值，分别是输入文件名与输出结果文件名
 300  Continue
      Read(100, *, End=400) namein, nameout
      Open(10, File=namein)
      Open(20, File=nameout)
!     niter是迭代次数。若为0则表示水均匀地分布在海一层。
      Print *, 'done reading from the input file: ', namein
!读入输入文件//

      Do l = 0, lsyn
        Do m = 0, l
          synthc(l, m) = 0.
          synths(l, m) = 0.
        EndDo
      EndDo

!//polar motion
      coefpm = (1.+rk(2))*(1.+rk2b-h2b)/(rkf-rk2b)
!     The following 2 lines put in the effects of polar motion feedback.
!     If you don't want to include that feedback, comment out these 2 lines.
      pmp = (1.+rk(2)-h(2)+coefpm)/(1.+rk(2))
      pmh = pmp*(1.+rk(2))*3.*rho0/rhoave/float(2*l+1)
!     ★注意：上面 pmh 一行原文中的 l 在循环结束后已无物理含义
!       （Do l = 0, lsyn 结束后 l = lsyn+1 = 181，即分母为 363）。
!       极移项只在 l=2, m=1 处生效，按物理意义分母应为 float(2*2+1)=5。
!       此处保留原文写法以便与文章代码逐行对照；如只需常规结果，
!       可把上面 3 行（coefpm/pmp/pmh）连同迭代中的极移分支一并注释掉。
!polar motion//

!//输入文件类型
      smass = 0.
      areatot = 0.

      dlon = 0.5
      dlat = 0.5            !分别为经度和纬度的间隔
      area1 = dlat*dlon*dtr*dtr*6.371E3**2
!     area1是不包括纬度因素的网格点面积

 50   Continue
      Read(10, *, End=60) xlon, xlat, thick
      If(thick<0) thick = 0

!     thick = thick / 100
!     读取数据依次为网格点经度、纬度、水高增量(m)

      xlat = 90. - xlat
      x1 = xlat - dlat/2.
      x2 = xlat + dlat/2.
      If(x1<0.) x1 = 0.
      If(x2>180.) x2 = 180.
      xlon = xlon*dtr
      xlat = xlat*dtr
      area = dlon*dtr*(dcos(x1*dtr)-dcos(x2*dtr))*6.371E3**2
!     area = area1*dsin(xlat)
      rmass = thick*100.0*1.00*(area*1.E10)
      smass = smass + rmass
      areatot = areatot + area

      Call gdisc(xlon, xlat, area, rmass, synthc, synths, lsyn, rk)

      Goto 50
 60   Continue
!输入文件类型//

!//此时，程序已经计算出由：[(施加的表面载荷)加上(该表面载荷引起的固体地球变形)]
!  等引起的重力势的球谐系数。结果存储在synthc、synths中。//

!//计算勒让德函数和cos(m*phi), sin(m*phi)
      Do j = 1, nth
        x = cos((90.-rlat(j))*dtr)

        Call martin(lmost, x, plmart, pdum)

        Do l = 0, lmax
          Do m = 0, l
            If(m/=0) Then
              plm(l, m, j) = plmart(l, m)*2.0
            Else
              plm(l, m, j) = plmart(l, m)*sqrt(2.0)
            EndIf
          EndDo
        EndDo
      EndDo

      Do i = 1, nphi
        Do m = 0, lmax
          phase = float(m)*rlon(i)*dtr
          ccos(m, i) = cos(phase)
          ssin(m, i) = sin(phase)
        EndDo
      EndDo
!计算勒让德函数和cos(m*phi), sin(m*phi)//

!//归一化谐波系数
      tmass = synthc(0, 0)*5.97E27
!     tmass是冰盖的质量(gm)
!     球谐系数乘以地球半径，这样的系数就是大地水准面的归一化谐波系数
      Do l = 0, lsyn
        Do m = 0, l
          synthc(l, m) = synthc(l, m)*arad
          synths(l, m) = synths(l, m)*arad
        EndDo
      EndDo
!归一化谐波系数//

!//整合海平面方程
      Call geoid(ofcn, rlon, rlat, plm, ccos, ssin, nth, nphi, lmost, 0, &
                 clm1, slm1)
      ocnint = clm1(0, 0)*4.*pi
!     Print *, 'ocnint: ', ocnint
!整合海平面方程//

!//迭代
      amass = -tmass/rho0/arad**2/ocnint
!     对于空间常数的0阶解，将ocn高度设为质量均匀分布后的高度
!     Print *, 'the ocean height increase, if the mass is distributed'
!     Print *, '  uniformly, is: ', amass

      Do i = 1, nphi
        Do j = 1, nth
          total(i, j) = amass*ofcn(i, j)
        EndDo
      EndDo

      Call geoid(total, rlon, rlat, plm, ccos, ssin, nth, nphi, lmost, lmax, &
                 hclm, hslm)
!     求出海平面高度的谐波系数，作为起始值

      If(niter==0) Goto 70

      Do n = 1, niter

!       Print *, 'about to start iteration #', n

        Do i = 1, nphi
          Do j = 1, nth
            total(i, j) = 0.
          EndDo
        EndDo

        Do i = 1, nphi
          Do l = 0, lmax
            Do m = 0, l
              temp = coefh(l)*(hclm(l, m)*ccos(m, i) + hslm(l, m)*ssin(m, i)) &
                   + coefp(l)*(synthc(l, m)*ccos(m, i) + synths(l, m)*ssin(m, i))

              If((l==2) .And. (m==1)) Then      !//polar motion//
                temp = pmh*(hclm(l, m)*ccos(m, i) + hslm(l, m)*ssin(m, i)) &
                     + pmp*(synthc(l, m)*ccos(m, i) + synths(l, m)*ssin(m, i))
              EndIf

              Do j = 1, nth
                total(i, j) = total(i, j) + temp*plm(l, m, j)*ofcn(i, j)
              EndDo
            EndDo
          EndDo
        EndDo

        Call geoid(total, rlon, rlat, plm, ccos, ssin, nth, nphi, lmost, 0, &
                   clm1, slm1)

        rint = clm1(0, 0)*4.*pi
!       Print *, 'integral: ', rint

        amass = (-tmass/rho0/arad**2-rint)/ocnint

        Do i = 1, nphi
          Do j = 1, nth
            total(i, j) = total(i, j) + amass*ofcn(i, j)
          EndDo
        EndDo

!       find the harmonic coeffs of sea level height
        Call geoid(total, rlon, rlat, plm, ccos, ssin, nth, nphi, lmost, lmax, &
                   hclm, hslm)

      EndDo

 70   Continue
!迭代//

!//输出文件
      zmass = hclm(0, 0)*arad**2*rho0*4.*pi/1.E15
!     Print *, 'after iterating, the mass in gton is (should = -', tmass/1.E15, '): ', zmass

      Do i = 1, nphi
        Do j = 1, nth
          Write(20, 22) rlon(i), rlat(j), total(i, j)
        EndDo
      EndDo
      Print *, 'done all from ', namein
!输出文件//

      Close(10)
      Close(20)
      Goto 300
 400  Continue

      Stop
End Program sleqn


!==============================================================================
      Subroutine martin(lmax, x, plm, ptemp)
!//使用Martin的递归关系计算归一化勒让德函数//

      Implicit Real*8 (A-H, O-Z)
      Dimension plm(0:lmax, 0:lmax), ptemp(0:lmax)

      rsin = sqrt(1.-x**2)

      Do l = 0, lmax
        Do m = 0, lmax
          plm(l, m) = 0.
        EndDo
      EndDo

      Do m = 0, lmax

        If(m==0) Then
          ptemp(0) = 1./sqrt(2.)
        Else
          ptemp(0) = 1.0
          Do j = 1, m
            ptemp(0) = ptemp(0)*sqrt(1.+1./2./float(j))
          EndDo
          ptemp(0) = ptemp(0)/sqrt(2.)
        EndIf

        If((lmax-m)>0) Then
          Do k = 1, lmax - m
            ptemp(k) = 2.*x*ptemp(k-1)*sqrt(1.+(float(m)-0.5)/float(k)) &
                     *sqrt(1.-(float(m)-0.5)/float(k+2*m))
            If(k>1) Then
              ptemp(k) = ptemp(k) - ptemp(k-2)*sqrt(1.+4./float(2*k+2*m-3)) &
                       *sqrt(1.-1./float(k))*sqrt(1.-1./float(k+2*m))
            EndIf
          EndDo
        EndIf

        Do l = m, lmax
          plm(l, m) = rsin**m*ptemp(l-m)
        EndDo

      EndDo

      Return
      End Subroutine martin


!==============================================================================
      Subroutine geoid(dens, rlon, rlat, plm, ccos, ssin, nth, nphi, &
                       lmost, lmax, clm1, slm1)
!//计算球谐系数（对 theta、phi 积分得到 l、m 阶斯托克斯系数）//

!//变量的定义与赋值
      Implicit Real*8 (A-H, O-Z)
      Dimension th(nth), phi(nphi), dens(nphi, nth), &
                rlat(nth), rlon(nphi), &
                clm1(0:lmost, 0:lmost), slm1(0:lmost, 0:lmost), &
                plm(0:lmost, 0:lmost, nth), &
                plm1(0:lmost, 0:lmost, nth), &
                ccos(0:lmost, nphi), ssin(0:lmost, nphi)

      If(lmax>lmost) Then
        Print *, 'error #35: ', lmax, lmost
        Stop
      EndIf

      pi = 3.14159265D0
      dtr = pi/180.D0
      dphi = 360./float(nphi)
      dth = 180./float(nth)
      dphi = dphi*dtr
      dth = dth*dtr
!     dth和dphi是theta和phi的间隔(在网格数据中)

      Do i = 1, nphi
        phi(i) = rlon(i)*dtr
      EndDo
      Do j = 1, nth
        th(j) = (90.D0-rlat(j))*dtr
      EndDo
!变量的定义与赋值//

!//将勒让德函数的值乘以sin(theta)*c保存在plm数组中
      Do i = 1, nth
        Do l = 0, lmax
          Do m = 0, l
            s = dsin(th(i))
            plm1(l, m, i) = plm(l, m, i)*dth*dphi*s
          EndDo
        EndDo
      EndDo
!将勒让德函数的值乘以sin(theta)*c保存在plm数组中//

!//通过对theta和phi积分，得到l和m的斯托克斯系数
      Do l = 0, lmax
        Do m = 0, l
          clm1(l, m) = 0.
          slm1(l, m) = 0.
        EndDo
      EndDo

      Do i = 1, nth
!       print *, 'about to start i= ', i, ' out of ', nth
        Do j = 1, nphi
          Do m = 0, lmax
            tempc = dens(j, i)*ccos(m, j)
            temps = dens(j, i)*ssin(m, j)
            Do l = m, lmax
              clm1(l, m) = clm1(l, m) + tempc*plm1(l, m, i)
              slm1(l, m) = slm1(l, m) + temps*plm1(l, m, i)
            EndDo
          EndDo
        EndDo
      EndDo

      Do m = 0, lmax
        Do l = m, lmax
          clm1(l, m) = clm1(l, m)/4./pi
          slm1(l, m) = slm1(l, m)/4./pi
        EndDo
      EndDo
!通过对theta和phi积分，得到l和m的斯托克斯系数//

      Return
      End Subroutine geoid


!==============================================================================
      Subroutine gdisc(rlon, rlat, area, rmass, clm1, slm1, lmost, rk)
!//计算均匀圆盘（单个网格单元）的斯托克斯系数//

      Parameter (lmax=180, lmax1=lmax+1)
      Implicit Real*8 (A-H, O-Z)
      Dimension plmart(0:lmax1, 0:lmax1), pdum(0:lmax1), rk(0:lmost), &
                temp(0:lmax), &
                clm1(0:lmost, 0:lmost), slm1(0:lmost, 0:lmost)

      If(lmost>lmax) Then
        Print *, 'error #5 ', lmost, lmax
        Stop
      EndIf

      pi = 3.14159265
      dtr = pi/180.

      clat = 1. - area/6.371E3**2/2./pi
      alpha = dcos(clat)
!     alpha是角半径(以度为单位)   ← 原文如此，该变量其后并未使用

      Call martin(lmax1, clat, plmart, pdum)

      Do l = 0, lmax1
        plmart(l, 0) = plmart(l, 0)*sqrt(2./float(2*l+1))
      EndDo
      Do l = 1, lmax
        temp(l) = (plmart(l-1, 0)-plmart(l+1, 0))/2.
      EndDo
      temp(0) = (1.-clat)/2.
      clat = cos(rlat)

      Call martin(lmax1, clat, plmart, pdum)

      Do l = 0, lmax
        Do m = 0, l
          plmart(l, m) = plmart(l, m)*sqrt(2.)
          If(m/=0) plmart(l, m) = plmart(l, m)*sqrt(2.)
        EndDo
      EndDo

      h = rmass/(area*1.E5**2)
!     h是水高，单位为cm
      ha = h/6.371E8
      Do l = 0, lmax
        Do m = 0, l
          wc = temp(l)/float(2*l+1)*plmart(l, m)*cos(m*rlon)
          ws = temp(l)/float(2*l+1)*plmart(l, m)*sin(m*rlon)
          clm1(l, m) = clm1(l, m) + wc*3./5.517*(1.+rk(l))/float(2*l+1)*ha
          slm1(l, m) = slm1(l, m) + ws*3./5.517*(1.+rk(l))/float(2*l+1)*ha
        EndDo
      EndDo

      Return
      End Subroutine gdisc
